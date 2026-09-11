import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  ConversationDetail,
  ConversationPatch,
  ConversationSummary,
  MessageOut,
  NoteOut,
  SendMessageRequest,
} from '../types'

export type ConversationFilter =
  | 'all'
  | 'mine'
  | 'unassigned'
  | 'overdue'
  | 'snoozed'
  | 'resolved'
  | 'archived'

const PAGE = 50

export function useConversations(filter: ConversationFilter, dept?: string | null) {
  const { propertyId } = useSession()
  return useInfiniteQuery<ConversationSummary[], ApiError>({
    queryKey: qk.conversations(propertyId, filter, dept),
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({
        filter,
        limit: String(PAGE),
        offset: String(pageParam as number),
      })
      if (dept) params.set('dept', dept)
      return api<ConversationSummary[]>(propertyPath(propertyId, `conversations?${params}`))
    },
    // Ruling R3: offset paging. A short page means the end.
    getNextPageParam: (last, all) =>
      last.length < PAGE ? undefined : all.reduce((n, p) => n + p.length, 0),
  })
}

export function useConversation(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<ConversationDetail, ApiError>({
    queryKey: qk.conversation(propertyId, id ?? ''),
    queryFn: () => api<ConversationDetail>(propertyPath(propertyId, `conversations/${id}`)),
    enabled: Boolean(id),
  })
}

export function useAddNote(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<NoteOut, ApiError, { body: string }>({
    mutationFn: (body) =>
      api<NoteOut>(propertyPath(propertyId, `conversations/${conversationId}/notes`), {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
    },
  })
}

export function usePatchConversation(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<ConversationDetail, ApiError, ConversationPatch>({
    mutationFn: (patch) =>
      api<ConversationDetail>(propertyPath(propertyId, `conversations/${conversationId}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: () => {
      // Assignment, status and snooze all change which filters this belongs to.
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
      void client.invalidateQueries({ queryKey: qk.conversationsAll(propertyId) })
    },
  })
}

let optimisticCounter = 0

export function useSendMessage(conversationId: string) {
  const { propertyId, user } = useSession()
  const client = useQueryClient()
  const key = qk.conversation(propertyId, conversationId)

  return useMutation<MessageOut, ApiError, SendMessageRequest, { optimisticId: string }>({
    mutationFn: (body) =>
      api<MessageOut>(propertyPath(propertyId, `conversations/${conversationId}/messages`), {
        method: 'POST',
        json: body,
      }),
    onMutate: async (body) => {
      await client.cancelQueries({ queryKey: key })
      const optimisticId = `optimistic-${++optimisticCounter}`
      client.setQueryData<ConversationDetail>(key, (current) =>
        current
          ? {
              ...current,
              messages: [
                ...current.messages,
                {
                  id: optimisticId,
                  conversationId,
                  direction: 'outbound',
                  channel: current.channelPrimary,
                  authorType: 'staff',
                  authorUserId: user.id,
                  body: body.body,
                  deliveryStatus: 'queued',
                  sentAt: null,
                  deliveredAt: null,
                  providerErrorCode: null,
                  providerErrorMessage: null,
                  digitalAssetId: body.digitalAssetId ?? null,
                  redacted: false,
                },
              ],
            }
          : current,
      )
      return { optimisticId }
    },
    onSuccess: (real, _body, context) => {
      client.setQueryData<ConversationDetail>(key, (current) =>
        current
          ? {
              ...current,
              messages: current.messages.map((m) => (m.id === context?.optimisticId ? real : m)),
            }
          : current,
      )
    },
    onError: (_error, _body, context) => {
      // A rejected send creates no server row (§6) — drop the bubble rather than leave a ghost.
      client.setQueryData<ConversationDetail>(key, (current) =>
        current
          ? { ...current, messages: current.messages.filter((m) => m.id !== context?.optimisticId) }
          : current,
      )
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: qk.conversationsAll(propertyId) })
    },
  })
}

export function useRetryMessage(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<MessageOut, ApiError, { messageId: string }>({
    mutationFn: ({ messageId }) =>
      api<MessageOut>(
        propertyPath(propertyId, `conversations/${conversationId}/messages/${messageId}/retry`),
        { method: 'POST' },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
    },
  })
}
