import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { sessionFixture, testQueryClient } from '../../test/harness'
import { qk } from '../queryKeys'
import { useChecklistLibrary, useImportChecklist } from './checklists'

function serve(body: unknown, status = 200) {
  vi.mocked(fetch).mockImplementation(() =>
    Promise.resolve(new Response(JSON.stringify(body), { status })),
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

function adminClient() {
  const client = testQueryClient()
  client.setQueryData(qk.session, sessionFixture({ role: 'admin' }))
  return client
}

describe('checklist library hooks', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => vi.unstubAllGlobals())

  it('loads the library only when asked', async () => {
    serve([{ key: 'night_audit' }])
    const client = adminClient()
    const { result, rerender } = renderHook(({ on }) => useChecklistLibrary(on), {
      wrapper: wrapper(client), initialProps: { on: false },
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
    rerender({ on: true })
    await waitFor(() => expect(result.current.data).toEqual([{ key: 'night_audit' }]))
    expect(String(vi.mocked(fetch).mock.calls[0]![0])).toBe('/api/p/prop-a/checklists/library')
  })

  it('imports by key with the department and name in the body, then refreshes checklists', async () => {
    serve({ id: 't-new' }, 201)
    const client = adminClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useImportChecklist(), { wrapper: wrapper(client) })
    act(() => {
      result.current.mutate({ key: 'night_audit', departmentId: 'dept-fd', name: 'Night Audit' })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [url, init] = vi.mocked(fetch).mock.calls[0]!
    expect(String(url)).toBe('/api/p/prop-a/checklists/library/night_audit/import')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ departmentId: 'dept-fd', name: 'Night Audit' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.ckAll('prop-a') })
  })
})
