import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../client'
import { qk } from '../queryKeys'
import type { GuestThread, SimEvent, SimGuest } from '../types'

export function useSimGuests() {
  return useQuery<SimGuest[], ApiError>({
    queryKey: qk.simGuests,
    queryFn: () => api<SimGuest[]>('/api/dev/sim/guests'),
  })
}

export function useSimThread(propertyId: string | undefined, phone: string | undefined) {
  return useQuery<GuestThread, ApiError>({
    queryKey: qk.simThread(propertyId ?? '', phone ?? ''),
    // Ruling R5: the server requires both params.
    queryFn: () =>
      api<GuestThread>(
        `/api/dev/sim/thread?phone=${encodeURIComponent(phone!)}&propertyId=${encodeURIComponent(propertyId!)}`,
      ),
    enabled: Boolean(propertyId && phone),
    // The simulator has no socket of its own; a 2s poll is simpler and dev-only.
    refetchInterval: 2000,
  })
}

export function useSimEvents() {
  return useQuery<SimEvent[], ApiError>({
    queryKey: qk.simEvents,
    queryFn: () => api<SimEvent[]>('/api/dev/sim/events'),
    refetchInterval: 2000,
  })
}

export function useSendInbound() {
  const client = useQueryClient()
  return useMutation<void, ApiError, { from: string; to: string; body: string }>({
    mutationFn: ({ from, to, body }) =>
      // Form-encoded with Twilio's field names, exactly as a real webhook arrives.
      api<void>('/api/hooks/sms/inbound', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Mock-Secret': 'dev',
        },
        body: new URLSearchParams({
          From: from,
          To: to,
          Body: body,
          MessageSid: `mock-${Math.random().toString(16).slice(2, 10)}`,
        }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['sim'] })
    },
  })
}
