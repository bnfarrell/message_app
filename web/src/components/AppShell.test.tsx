import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../api/types'
import { SessionProvider } from '../auth/SessionContext'
import { ThemeProvider } from '../theme/ThemeContext'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { AppShell } from './AppShell'

function mount(
  opts: { role?: Role; withSecondProperty?: boolean; secondRole?: Role; unreadCount?: number } = {},
) {
  return renderWithProviders(
    <SessionProvider>
      <ThemeProvider>
        <AppShell unreadCount={opts.unreadCount}>
          <p>screen body</p>
        </AppShell>
      </ThemeProvider>
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

  it('hides the Inbox from corporate, which cannot reply', async () => {
    mount({ role: 'corporate' })
    expect(await screen.findByRole('link', { name: /analytics/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /inbox/i })).not.toBeInTheDocument()
  })

  it('shows Admin only to admin', async () => {
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

  it('shows an unread badge on Alerts only when there is something unread', async () => {
    const { unmount } = mount({ role: 'agent', unreadCount: 3 })
    expect(await screen.findByTestId('unread-badge')).toHaveTextContent('3')
    unmount()
    mount({ role: 'agent', unreadCount: 0 })
    expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument()
  })

  it('names the signed-in user and their role', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByText('Ava')).toBeInTheDocument()
    expect(screen.getByText('Agent')).toBeInTheDocument()
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
})
