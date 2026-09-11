import { screen } from '@testing-library/react'
import { useEffect } from 'react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { RequireAuth } from './RequireAuth'
import { ACTIVE_PROPERTY_KEY } from './storage'

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

function mount(child = <ExpiringScreen />, { seeded = true } = {}) {
  return renderWithProviders(
    <Routes>
      <Route path="/app" element={<RequireAuth />}>
        <Route index element={child} />
      </Route>
      <Route path="/login" element={<div>Login Screen</div>} />
    </Routes>,
    // Unseeded means /api/auth/me is genuinely in flight on the first render — the cold start.
    { route: '/app', session: seeded ? sessionFixture({ role: 'agent' }) : undefined },
  )
}

describe('RequireAuth — mid-session expiry', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
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
  // Ruling D56. The explicit sign-out path clears this key in useLogout's onSettled, but a
  // session that dies on its own never runs that mutation — RequireAuth just redirects. On a
  // shared front-desk terminal the stored property then outlives its owner's session.
  it('clears the stored active property when the session dies without a sign-out', async () => {
    localStorage.setItem(ACTIVE_PROPERTY_KEY, 'prop-a')
    vi.stubGlobal('fetch', vi.fn(async () => unauthorizedResponse()))

    mount()

    expect(await screen.findByText('Login Screen', undefined, { timeout: 2000 })).toBeInTheDocument()
    expect(localStorage.getItem(ACTIVE_PROPERTY_KEY)).toBeNull()
  })

  // The condition is `!isPending && ...`, and `isPending` is doing real work: on a cold start
  // `data` is undefined until /api/auth/me answers, so without it every page load would clear
  // the preference SessionProvider is about to read one render later.
  it('leaves the stored property alone through a cold start that succeeds', async () => {
    localStorage.setItem(ACTIVE_PROPERTY_KEY, 'prop-a')
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(sessionFixture()), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })))

    mount(<div>Protected</div>, { seeded: false })

    expect(await screen.findByText('Protected')).toBeInTheDocument()
    expect(localStorage.getItem(ACTIVE_PROPERTY_KEY)).toBe('prop-a')
  })
})
