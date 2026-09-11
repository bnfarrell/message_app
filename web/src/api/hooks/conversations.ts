import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { ConversationDetail, ConversationSummary } from '../types'

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
