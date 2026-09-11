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
    //
    // Task 18's Shell fires a real fetch (useUnreadCount) for every /app/* route, session or
    // not — under a blanket 401 that trips RequireAuth's onUnauthorized handler and bounces a
    // role-seeded test straight to /login, which is not what any of these tests are about (the
    // admin route previously never fetched anything, so this race did not exist before Task 18).
    // Only that one endpoint is special-cased; everything else keeps 401ing as before.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        if (String(input).includes('unread-count')) {
          return Promise.resolve(
            new Response(JSON.stringify({ count: 0 }), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }),
          )
        }
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Not signed in' } }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }),
    )
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends an agent from /app to the inbox', async () => {
    mountAt('/app', 'agent')
    // Task 12 replaced the Inbox placeholder with the real screen, which has no literal
    // "Inbox" text of its own in <main> — the location is the stable signal that we landed.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/inbox'))
  })

  it('sends dept_staff from /app to the board, filtered to mine', async () => {
    mountAt('/app', 'dept_staff')
    // Task 16 replaced the Board placeholder with the real screen, which has no literal
    // "Board" text of its own in <main> — the location is the stable signal that we landed.
    // It also fetches on mount, which the blanket 401 in this file's beforeEach fails, so
    // this is the only thing in this file that would catch <Navigate> silently dropping
    // `?mine=1` on the way there.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/board?mine=1'))
  })

  it('sends a supervisor from /app to the board, filtered to mine', async () => {
    mountAt('/app', 'supervisor')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/board?mine=1'))
  })

  it('sends a manager from /app to analytics', async () => {
    mountAt('/app', 'manager')
    // Task 17 replaced the Analytics placeholder with the real screen, which fetches on
    // mount and (like Task 16's board) fails that fetch under this file's blanket 401 mock —
    // so the location is the stable signal that we landed, not the screen's own "Analytics" text.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/analytics'))
  })

  it('sends an admin from /app to analytics', async () => {
    mountAt('/app', 'admin')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/analytics'))
  })

  it('sends corporate from /app to analytics', async () => {
    mountAt('/app', 'corporate')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/analytics'))
  })

  it('keeps an agent out of analytics, bouncing them to their landing screen', async () => {
    mountAt('/app/analytics', 'agent')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/inbox'))
  })

  it('keeps a manager out of admin', async () => {
    mountAt('/app/admin/users', 'manager')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/analytics'))
    const main = await mainScreen()
    expect(main.queryByText('Admin')).not.toBeInTheDocument()
  })

  it('lets an admin into admin', async () => {
    mountAt('/app/admin/users', 'admin')
    expect(await (await mainScreen()).findByText('Admin')).toBeInTheDocument()
  })

  it('redirects an unknown path to /app', async () => {
    mountAt('/nonsense', 'agent')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/inbox'))
  })

  it('sends an unauthenticated visitor to /login', async () => {
    renderWithProviders(<AppRoutes />, { route: '/app/inbox' })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument(),
    )
  })
})
