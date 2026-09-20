import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { sessionFixture, testQueryClient } from '../../test/harness'
import { qk } from '../queryKeys'
import { useCreateLogEntry } from './log'

function serve(status = 201, body: unknown = { id: 'e-1' }) {
  vi.mocked(fetch).mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
    ),
  )
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    )
  }
}

describe('useCreateLogEntry', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('carries linkedWorkOrderId and linkedConversationId over multipart when a photo is attached', async () => {
    const client = testQueryClient()
    client.setQueryData(qk.session, sessionFixture({ role: 'agent' }))
    const { result } = renderHook(() => useCreateLogEntry(), { wrapper: wrapper(client) })

    const photo = new File(['bytes'], 'x.png', { type: 'image/png' })
    act(() => {
      result.current.mutate({
        body: 'note',
        mentions: [],
        ackAudience: [],
        requiresAck: false,
        linkedWorkOrderId: 'wo-1',
        linkedConversationId: 'conv-1',
        photo,
      })
    })

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled())
    const [, init] = vi.mocked(fetch).mock.calls[0]!
    const form = init!.body as FormData
    // The bug this guards against: the multipart branch forwarded body/departmentId/mentions/
    // requiresAck/ackAudience/photo but silently dropped both link ids, unlike the JSON branch
    // which sends the whole object.
    expect(form.get('linkedWorkOrderId')).toBe('wo-1')
    expect(form.get('linkedConversationId')).toBe('conv-1')
  })
})
