import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../api/types'
import { RequireAuth } from '../auth/RequireAuth'
import { SessionProvider } from '../auth/SessionContext'
import { ThemeProvider } from '../theme/ThemeContext'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { AppShell } from './AppShell'
import { visibleNavGroups } from './navModel'

// Reports where the router actually landed after a property switch — the thing at risk
// is the navigation target, not just that setPropertyId was called.
function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

// Routes by query text so ThemeContext's own matchMedia('(prefers-color-scheme: dark)')
// call — made by every AppShell render — still gets an answer instead of throwing.
function stubMobileViewport(isMobile: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: query.includes('max-width') && isMobile,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    })),
  )
}

function mount(
  opts: {
    role?: Role
    withSecondProperty?: boolean
    secondRole?: Role
    unreadCount?: number
    route?: string
  } = {},
) {
  return renderWithProviders(
    <SessionProvider>
      <ThemeProvider>
        <AppShell unreadCount={opts.unreadCount}>
          <p>screen body</p>
        </AppShell>
      </ThemeProvider>
    </SessionProvider>,
    { session: sessionFixture(opts), route: opts.route ?? '/app/inbox' },
  )
}

function mountWithLocation(
  opts: { role?: Role; withSecondProperty?: boolean; secondRole?: Role; unreadCount?: number } = {},
) {
  return renderWithProviders(
    <SessionProvider>
      <ThemeProvider>
        <AppShell unreadCount={opts.unreadCount}>
          <p>screen body</p>
        </AppShell>
      </ThemeProvider>
      <LocationDisplay />
    </SessionProvider>,
    { session: sessionFixture(opts), route: '/app/inbox' },
  )
}

describe('AppShell', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the screen body and the property identity', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByText('screen body')).toBeInTheDocument()
    expect(screen.getByText('Harbourview Hotel')).toBeInTheDocument()
    expect(screen.getByText('HVH')).toBeInTheDocument()
  })

  it('shows an agent Inbox, Board and Alerts but not Analytics or Admin', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByRole('link', { name: /inbox/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /board/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /alerts/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /analytics/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /admin/i })).not.toBeInTheDocument()
  })

  it('shows the Inbox to corporate, which can read conversations and add notes', async () => {
    // corporate holds view_all_conversations and add_note on the server
    // (server/app/auth/permissions.py), so the Inbox is reachable — read-only.
    mount({ role: 'corporate' })
    expect(await screen.findByRole('link', { name: /analytics/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /inbox/i })).toBeInTheDocument()
    // It cannot reply, so no Board: create_work_order and close_work_order are both false.
    expect(screen.queryByRole('link', { name: /board/i })).not.toBeInTheDocument()
  })

  it('shows Admin to a role with manage_admin', async () => {
    // manage_admin is {admin, corporate} on the server — admin is not the only role
    // that sees this link, so this only asserts admin sees it, not exclusivity.
    mount({ role: 'admin' })
    expect(await screen.findByRole('link', { name: /admin/i })).toBeInTheDocument()
  })

  it('marks the current route as the active nav item', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByRole('link', { name: /inbox/i })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: /board/i })).not.toHaveAttribute('aria-current')
  })

  it('keeps the Admin rail entry lit on every screen inside the section', async () => {
    // Reported from the running app: the Admin pill lit only on Users & roles, because
    // /app/admin/departments is a sibling of the link's target, not a descendant of it.
    const { unmount } = mount({ role: 'admin', route: '/app/admin/departments' })
    expect(await screen.findByRole('link', { name: /admin/i })).toHaveAttribute(
      'aria-current',
      'page',
    )
    unmount()

    mount({ role: 'admin', route: '/app/admin/users' })
    expect(await screen.findByRole('link', { name: /admin/i })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('does not light the Admin entry from outside the section', async () => {
    mount({ role: 'admin', route: '/app/analytics' })
    expect(await screen.findByRole('link', { name: /admin/i })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('link', { name: /analytics/i })).toHaveAttribute('aria-current', 'page')
  })

  it('keeps Board lit on a work order, which lives outside /app/board', async () => {
    mount({ role: 'supervisor', route: '/app/work-orders/w-204' })
    expect(await screen.findByRole('link', { name: /board/i })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('shows an unread badge on Alerts only when there is something unread', async () => {
    const { unmount } = mount({ role: 'agent', unreadCount: 3 })
    expect(await screen.findByTestId('unread-badge')).toHaveTextContent('3')
    unmount()
    mount({ role: 'agent', unreadCount: 0 })
    expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument()
  })

  it('names the signed-in user and their role', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByText('Ava Nolan')).toBeInTheDocument()
    expect(screen.getByText('Agent')).toBeInTheDocument()
  })

  it('groups the rail under uppercase section headings', async () => {
    mount({ role: 'admin' })
    // The headings are structure, not decoration: they are what tells an operator that
    // Analytics is a different kind of destination from Inbox.
    expect(await screen.findByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Insights')).toBeInTheDocument()
    expect(screen.getByText('Admin', { selector: 'p' })).toBeInTheDocument()
  })

  it('renders nothing at all for a group whose every item is filtered out', async () => {
    // An agent has neither view_property_analytics nor manage_admin, so INSIGHTS and ADMIN
    // are empty. An empty heading would advertise a section the user cannot enter.
    mount({ role: 'agent' })
    expect(await screen.findByText('Overview')).toBeInTheDocument()
    expect(screen.queryByText('Insights')).not.toBeInTheDocument()
    expect(screen.queryByText('Admin', { selector: 'p' })).not.toBeInTheDocument()
  })

  it('keeps only the capability-free items when a role can do nothing at all', () => {
    // Asserted on the model rather than mimed through a role: no role in the product holds
    // zero capabilities, and this is what guarantees the rail never renders a bare heading.
    const groups = visibleNavGroups(() => false)
    expect(groups.map((g) => g.heading)).toEqual(['Overview'])
    expect(groups[0]!.items.map((i) => i.label)).toEqual(['Alerts', 'Messages'])
  })

  it('keeps the property lockup as plain text, not a dead button, for one membership', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByText('Harbourview Hotel')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /switch property/i })).not.toBeInTheDocument()
  })

  it('carries the property switcher on the lockup, not at the foot of the rail', async () => {
    mount({ role: 'agent', withSecondProperty: true })
    // Ruling D64. The accessible name has to survive the move: the visible label is now the
    // property itself, so the intent is carried by a visually hidden word.
    const trigger = await screen.findByRole('button', { name: /switch property/i })
    expect(trigger).toHaveTextContent('Harbourview Hotel')
  })

  it('toggles the theme from the nav', async () => {
    mount({ role: 'agent' })
    await userEvent.click(await screen.findByRole('button', { name: /theme/i }))
    await vi.waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
  })

  it('hides the property switcher for a single-property user', async () => {
    mount({ role: 'agent' })
    await screen.findByText('Harbourview Hotel')
    expect(screen.queryByRole('button', { name: /switch property/i })).not.toBeInTheDocument()
  })

  it('offers a property switcher when the user has two memberships', async () => {
    mount({ role: 'agent', withSecondProperty: true })
    await userEvent.click(await screen.findByRole('button', { name: /switch property/i }))
    expect(screen.getByRole('menuitem', { name: /Lakeside Inn/ })).toBeInTheDocument()
  })

  it('switching property stores the choice', async () => {
    mount({ role: 'agent', withSecondProperty: true })
    await userEvent.click(await screen.findByRole('button', { name: /switch property/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Lakeside Inn/ }))
    expect(localStorage.getItem('activePropertyId')).toBe('prop-b')
  })

  it('switching to a property where the role differs lands on that role landing screen', async () => {
    // Agent at Harbourview, admin at Lakeside — the switch must route by the *target*
    // membership's role, not the current session's role.
    mountWithLocation({ role: 'agent', withSecondProperty: true, secondRole: 'admin' })
    await userEvent.click(await screen.findByRole('button', { name: /switch property/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Lakeside Inn/ }))
    expect(await screen.findByTestId('location')).toHaveTextContent('/app/analytics')
    expect(screen.getByTestId('location')).not.toHaveTextContent('/app/inbox')
  })

  it('signs out through RequireAuth and lands on /login, without looping /api/auth/me', async () => {
    let logoutCalls = 0
    let meCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/auth/logout')) {
          logoutCalls += 1
          return new Response(null, { status: 204 })
        }
        if (url.includes('/api/auth/me')) {
          meCalls += 1
          return new Response(
            JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Signed out' } }),
            { status: 401, headers: { 'Content-Type': 'application/json' } },
          )
        }
        return new Response(null, { status: 204 })
      }),
    )

    renderWithProviders(
      <Routes>
        <Route path="/app" element={<RequireAuth />}>
          <Route
            index
            element={
              <ThemeProvider>
                <AppShell>
                  <p>screen body</p>
                </AppShell>
              </ThemeProvider>
            }
          />
        </Route>
        <Route path="/login" element={<div>Login Screen</div>} />
      </Routes>,
      { route: '/app', session: sessionFixture({ role: 'agent' }) },
    )

    await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))

    expect(await screen.findByText('Login Screen')).toBeInTheDocument()
    expect(logoutCalls).toBe(1)
    // A refetch loop would keep calling /api/auth/me indefinitely; RequireAuth's in-flight
    // guard should coalesce the post-logout refetch(es) into at most one extra call.
    // Clearing the query cache re-triggers the session query once (data is gone, so the
    // active observer refetches); that single 401 redirects without looping.
    expect(meCalls).toBe(1)
  })

  describe('on a narrow viewport', () => {
    afterEach(() => {
      vi.unstubAllGlobals()
    })

    it('replaces the rail with the bottom nav', async () => {
      stubMobileViewport(true)
      mount({ role: 'agent' })
      expect(await screen.findByRole('link', { name: /inbox/i })).toBeInTheDocument()
      // The rail is the only place these section headings render.
      expect(screen.queryByText('Overview')).not.toBeInTheDocument()
    })

    it('moves the property identity into the header', async () => {
      stubMobileViewport(true)
      mount({ role: 'agent' })
      expect(await screen.findByText('Harbourview Hotel')).toBeInTheDocument()
    })

    it('still offers the property switcher from the header', async () => {
      stubMobileViewport(true)
      mount({ role: 'agent', withSecondProperty: true })
      const trigger = await screen.findByRole('button', { name: /switch property/i })
      await userEvent.click(trigger)
      expect(screen.getByRole('menuitem', { name: /Lakeside Inn/ })).toBeInTheDocument()
    })

    it('keeps the rail for a wide viewport', async () => {
      stubMobileViewport(false)
      mount({ role: 'agent' })
      expect(await screen.findByText('Overview')).toBeInTheDocument()
    })
  })
})
