import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { ConversationDetail, ConversationPatch, ConversationSummary, NoteOut } from '../types'

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
