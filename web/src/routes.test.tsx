import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from './api/types'
import { AppRoutes } from './routes'
import { renderWithProviders, sessionFixture } from './test/harness'

function mountAt(route: string, role: Role) {
  return renderWithProviders(<AppRoutes />, { route, session: sessionFixture({ role }) })
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
    expect(await screen.findByText('Inbox')).toBeInTheDocument()
  })

  it('sends dept_staff from /app to the board', async () => {
    mountAt('/app', 'dept_staff')
    expect(await screen.findByText('Board')).toBeInTheDocument()
  })

  it('sends a manager from /app to analytics', async () => {
    mountAt('/app', 'manager')
    expect(await screen.findByText('Analytics')).toBeInTheDocument()
  })

  it('keeps an agent out of analytics, bouncing them to their landing screen', async () => {
    mountAt('/app/analytics', 'agent')
    expect(await screen.findByText('Inbox')).toBeInTheDocument()
    expect(screen.queryByText('Analytics')).not.toBeInTheDocument()
  })

  it('keeps a manager out of admin', async () => {
    mountAt('/app/admin/users', 'manager')
    expect(await screen.findByText('Analytics')).toBeInTheDocument()
    expect(screen.queryByText('Admin')).not.toBeInTheDocument()
  })

  it('lets an admin into admin', async () => {
    mountAt('/app/admin/users', 'admin')
    expect(await screen.findByText('Admin')).toBeInTheDocument()
  })

  it('redirects an unknown path to /app', async () => {
    mountAt('/nonsense', 'agent')
    expect(await screen.findByText('Inbox')).toBeInTheDocument()
  })

  it('sends an unauthenticated visitor to /login', async () => {
    renderWithProviders(<AppRoutes />, { route: '/app/inbox' })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument(),
    )
  })
})
