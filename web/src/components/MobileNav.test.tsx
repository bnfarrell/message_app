import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Capability } from '../auth/capabilities'
import { renderWithProviders } from '../test/harness'
import { MobileNav } from './MobileNav'
import { visibleNavGroups } from './navModel'

function mount(can: (capability: Capability) => boolean, opts: { route?: string; unreadCount?: number } = {}) {
  return renderWithProviders(
    <MobileNav groups={visibleNavGroups(can)} unreadCount={opts.unreadCount} />,
    { route: opts.route ?? '/app/board' },
  )
}

const agentCan = (c: Capability) =>
  (['reply', 'assign', 'add_note', 'archive', 'create_work_order', 'view_own_stats'] as Capability[]).includes(c)
const adminCan = () => true

describe('MobileNav', () => {
  it('shows Inbox, Board and Alerts as direct tabs for a role without Insights/Admin', async () => {
    mount(agentCan)
    expect(await screen.findByRole('link', { name: /inbox/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /board/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /alerts/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /more/i })).not.toBeInTheDocument()
  })

  it('folds Analytics and Admin under a More tab for a role that can see them', async () => {
    mount(adminCan)
    expect(await screen.findByRole('button', { name: /more/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /analytics/i })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /more/i }))
    expect(screen.getByRole('menuitem', { name: /analytics/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /^admin$/i })).toBeInTheDocument()
  })

  it('marks the current route active on a direct tab', async () => {
    mount(agentCan, { route: '/app/board' })
    expect(await screen.findByRole('link', { name: /board/i })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: /inbox/i })).not.toHaveAttribute('aria-current')
  })

  it('marks More active when the current route is inside a folded section', async () => {
    mount(adminCan, { route: '/app/analytics' })
    expect(await screen.findByRole('button', { name: /more/i })).toHaveAttribute('aria-current', 'page')
  })

  it('shows an unread badge on Alerts when there is something unread', async () => {
    mount(agentCan, { unreadCount: 4 })
    expect(await screen.findByTestId('unread-badge')).toHaveTextContent('4')
  })

  it('closes the More menu on outside click', async () => {
    mount(adminCan)
    await userEvent.click(await screen.findByRole('button', { name: /more/i }))
    expect(screen.getByRole('menuitem', { name: /analytics/i })).toBeInTheDocument()

    await userEvent.click(document.body)
    expect(screen.queryByRole('menuitem', { name: /analytics/i })).not.toBeInTheDocument()
  })
})
