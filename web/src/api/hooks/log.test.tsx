import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { sessionFixture, testQueryClient } from '../../test/harness'
import { qk } from '../queryKeys'
import { useAdminLogTemplates, useCreateLogEntry, useLogTemplates, usePatchLogTemplate } from './log'

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

  it('carries templateId and fieldValues over multipart, and an empty body for notes', async () => {
    const client = testQueryClient()
    client.setQueryData(qk.session, sessionFixture({ role: 'agent' }))
    const { result } = renderHook(() => useCreateLogEntry(), { wrapper: wrapper(client) })

    const photo = new File(['bytes'], 'x.png', { type: 'image/png' })
    const fieldValues = [{ fieldId: 'f-occ', value: 87 }]
    act(() => {
      result.current.mutate({ templateId: 't-night', fieldValues, photo })
    })

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled())
    const form = vi.mocked(fetch).mock.calls[0]![1]!.body as FormData
    expect(form.get('templateId')).toBe('t-night')
    expect(JSON.parse(String(form.get('fieldValues')))).toEqual(fieldValues)
    expect(form.get('body')).toBe('')
  })
})

describe('log template hooks', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve(200, [])
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads the picker from log-entries/templates and the admin list from log-templates', async () => {
    const client = testQueryClient()
    client.setQueryData(qk.session, sessionFixture({ role: 'admin' }))
    renderHook(() => { useLogTemplates(); useAdminLogTemplates() }, { wrapper: wrapper(client) })

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2))
    const urls = vi.mocked(fetch).mock.calls.map(([input]) => String(input))
    expect(urls).toContain('/api/p/prop-a/log-entries/templates')
    expect(urls).toContain('/api/p/prop-a/log-templates')
  })

  it('patches by id and refreshes both template lists', async () => {
    const client = testQueryClient()
    client.setQueryData(qk.session, sessionFixture({ role: 'admin' }))
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => usePatchLogTemplate(), { wrapper: wrapper(client) })

    act(() => {
      result.current.mutate({ id: 't-1', active: false })
    })

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['logTemplates', 'prop-a'] }))
    const [input, init] = vi.mocked(fetch).mock.calls[0]!
    expect(String(input)).toBe('/api/p/prop-a/log-templates/t-1')
    expect(init!.method).toBe('PATCH')
    expect(JSON.parse(String(init!.body))).toEqual({ active: false })
  })
})
