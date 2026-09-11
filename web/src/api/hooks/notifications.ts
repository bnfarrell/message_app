import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { NotificationOut, UnreadCount } from '../types'

export function useNotifications(unreadOnly: boolean) {
  const { propertyId } = useSession()
  return useQuery<NotificationOut[], ApiError>({
    queryKey: qk.notifications(propertyId, unreadOnly),
    queryFn: () =>
      api<NotificationOut[]>(
        propertyPath(propertyId, `notifications${unreadOnly ? '?unread=1' : ''}`),
      ),
  })
}

export function useUnreadCount() {
  const { propertyId } = useSession()
  return useQuery<UnreadCount, ApiError>({
    queryKey: qk.unreadCount(propertyId),
    queryFn: () => api<UnreadCount>(propertyPath(propertyId, 'notifications/unread-count')),
    // The socket invalidates this; the interval is a backstop for a dropped connection.
    refetchInterval: 60_000,
  })
}

function useInvalidateNotifications() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: qk.notificationsAll(propertyId) })
    void client.invalidateQueries({ queryKey: qk.unreadCount(propertyId) })
  }
}

export function useMarkRead() {
  const { propertyId } = useSession()
  const invalidate = useInvalidateNotifications()
  return useMutation<void, ApiError, { id: string }>({
    mutationFn: ({ id }) =>
      api<void>(propertyPath(propertyId, `notifications/${id}/read`), { method: 'POST' }),
    onSuccess: invalidate,
  })
}

export function useMarkAllRead() {
  const { propertyId } = useSession()
  const invalidate = useInvalidateNotifications()
  return useMutation<void, ApiError, void>({
    mutationFn: () =>
      api<void>(propertyPath(propertyId, 'notifications/read-all'), { method: 'POST' }),
    onSuccess: invalidate,
  })
}
