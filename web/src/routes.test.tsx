import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useLocation } from 'react-router-dom'
import type { Role } from './api/types'
import { AppRoutes } from './routes'
import { renderWithProviders, sessionFixture } from './test/harness'

// Reports where the router actually landed, query string included — the Placeholder
// screen renders identically regardless of query, so a dropped `?mine=1` would
// otherwise be invisible to every assertion in this file.
function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}

function mountAt(route: string, role: Role) {
  return renderWithProviders(
    <>
      <AppRoutes />
      <LocationDisplay />
    </>,
    { route, session: sessionFixture({ role }) },
  )
}

// Task 9's AppShell nav repeats the same labels ("Inbox", "Board", ...) as these
// Placeholder screen titles, so queries here must be scoped to the routed screen body
// (the <main> landmark) rather than matching text anywhere in the shell, nav included.
async function mainScreen() {
  return within(await screen.findByRole('main'))
}

describe('AppRoutes', () => {
  beforeEach(() => {
    // Every mounted-with-a-role test pre-seeds the session into the query cache (staleTime:
    // Infinity), so /api/auth/me is never actually fetched for them; this default only fires
    // for the one unauthenticated test below. A 204 there makes api() return undefined, which
    // React Query logs as an error ("Query data cannot be undefined") even though the redirect
    // it drives is correct — a 401, what /api/auth/me really returns when signed out, avoids
    // that noise without changing what any test asserts.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Not signed in' } }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends an agent from /app to the inbox', async () => {
    mountAt('/app', 'agent')
    expect(await (await mainScreen()).findByText('Inbox')).toBeInTheDocument()
  })

  it('sends dept_staff from /app to the board, filtered to mine', async () => {
    mountAt('/app', 'dept_staff')
    expect(await (await mainScreen()).findByText('Board')).toBeInTheDocument()
    // The Placeholder ignores query strings entirely, so this is the only thing in this
    // file that would catch <Navigate> silently dropping `?mine=1` on the way there.
    expect(screen.getByTestId('location')).toHaveTextContent('/app/board?mine=1')
  })

  it('sends a supervisor from /app to the board, filtered to mine', async () => {
    mountAt('/app', 'supervisor')
    expect(await (await mainScreen()).findByText('Board')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/app/board?mine=1')
  })

  it('sends a manager from /app to analytics', async () => {
    mountAt('/app', 'manager')
    expect(await (await mainScreen()).findByText('Analytics')).toBeInTheDocument()
  })

  it('sends an admin from /app to analytics', async () => {
    mountAt('/app', 'admin')
    expect(await (await mainScreen()).findByText('Analytics')).toBeInTheDocument()
  })

  it('sends corporate from /app to analytics', async () => {
    mountAt('/app', 'corporate')
    expect(await (await mainScreen()).findByText('Analytics')).toBeInTheDocument()
  })

  it('keeps an agent out of analytics, bouncing them to their landing screen', async () => {
    mountAt('/app/analytics', 'agent')
    const main = await mainScreen()
    expect(await main.findByText('Inbox')).toBeInTheDocument()
    expect(main.queryByText('Analytics')).not.toBeInTheDocument()
  })

  it('keeps a manager out of admin', async () => {
    mountAt('/app/admin/users', 'manager')
    const main = await mainScreen()
    expect(await main.findByText('Analytics')).toBeInTheDocument()
    expect(main.queryByText('Admin')).not.toBeInTheDocument()
  })

  it('lets an admin into admin', async () => {
    mountAt('/app/admin/users', 'admin')
    expect(await (await mainScreen()).findByText('Admin')).toBeInTheDocument()
  })

  it('redirects an unknown path to /app', async () => {
    mountAt('/nonsense', 'agent')
    expect(await (await mainScreen()).findByText('Inbox')).toBeInTheDocument()
  })

  it('sends an unauthenticated visitor to /login', async () => {
    renderWithProviders(<AppRoutes />, { route: '/app/inbox' })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument(),
    )
  })
})
