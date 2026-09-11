import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../client'
import { qk } from '../queryKeys'
import type { LoginRequest, SessionOut } from '../types'

export function useSessionQuery() {
  return useQuery<SessionOut, ApiError>({
    queryKey: qk.session,
    queryFn: () => api<SessionOut>('/api/auth/me'),
    // A 401 here is the answer ("not logged in"), not a transient failure worth retrying.
    retry: false,
    staleTime: Infinity,
  })
}

export function useLogin() {
  const client = useQueryClient()
  return useMutation<SessionOut, ApiError, LoginRequest>({
    mutationFn: (body) => api<SessionOut>('/api/auth/login', { method: 'POST', json: body }),
    onSuccess: (session) => {
      client.setQueryData(qk.session, session)
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () => api<void>('/api/auth/logout', { method: 'POST' }),
    // Clear unconditionally: a failed logout must not leave another user's cache on screen.
    onSettled: () => {
      client.clear()
    },
  })
}
