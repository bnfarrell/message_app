import { screen } from '@testing-library/react'
import { useEffect } from 'react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { RequireAuth } from './RequireAuth'

// Fires two API calls that each independently discover the dead session at roughly the
// same time — the way two components each awaiting their own query might on a screen
// with more than one data source.
function ExpiringScreen() {
  useEffect(() => {
    void api('/api/dead-endpoint-a').catch(() => {})
    void api('/api/dead-endpoint-b').catch(() => {})
  }, [])
  return <div>Protected</div>
}

function unauthorizedResponse() {
  return new Response(
    JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Session expired' } }),
    { status: 401, headers: { 'Content-Type': 'application/json' } },
  )
}

function mount() {
  return renderWithProviders(
    <Routes>
      <Route path="/app" element={<RequireAuth />}>
        <Route index element={<ExpiringScreen />} />
      </Route>
      <Route path="/login" element={<div>Login Screen</div>} />
    </Routes>,
    { route: '/app', session: sessionFixture({ role: 'agent' }) },
  )
}

describe('RequireAuth — mid-session expiry', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // Task 12 fixed an unbounded loop here: a 401 fired refetch(), which itself 401s (the
  // session really is dead), which would re-invoke the same handler and refetch forever.
  // This pins both halves of that fix: the redirect still fires (not over-corrected to
  // never redirect) and it fires from a single coalesced refetch, not once per 401 (not
  // still looping).
  it('redirects to /login exactly once when the session dies mid-request, coalescing concurrent 401s', async () => {
    let meCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/auth/me')) meCalls += 1
        return unauthorizedResponse()
      }),
    )

    mount()

    // Bounded on purpose: if the redirect never happens this must fail legibly rather than
    // hang the run out to the suite-level timeout.
    expect(await screen.findByText('Login Screen', undefined, { timeout: 2000 })).toBeInTheDocument()
    // Two 401s fired close together must coalesce into a single refetch of /api/auth/me,
    // not one per 401 — that's the loop the useRef guard in RequireAuth prevents.
    expect(meCalls).toBe(1)
  })
})
