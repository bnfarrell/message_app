import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../api/types'
import { SessionProvider } from '../auth/SessionContext'
import { ThemeProvider } from '../theme/ThemeContext'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { CommandPalette } from './CommandPalette'

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function mount(opts: { role?: Role; withSecondProperty?: boolean; secondRole?: Role } = {}) {
  return renderWithProviders(
    <SessionProvider>
      <ThemeProvider>
        {/* A text box outside the palette: Ctrl+K must not be stolen from the composer. */}
        <textarea aria-label="Composer" />
        <CommandPalette />
      </ThemeProvider>
      <LocationDisplay />
    </SessionProvider>,
    { session: sessionFixture(opts), route: '/app/inbox' },
  )
}

const optionNames = () =>
  screen.getAllByRole('option').map((o) => o.textContent?.trim())

describe('CommandPalette', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens on Ctrl+K and closes on Escape, returning focus to the trigger', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    const trigger = await screen.findByRole('button', { name: /jump to a screen/i })

    await user.keyboard('{Control>}k{/Control}')
    const dialog = screen.getByRole('dialog', { name: /command palette/i })
    expect(within(dialog).getByRole('combobox')).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('opens on Cmd+K too', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await screen.findByRole('button', { name: /jump to a screen/i })
    await user.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByRole('dialog', { name: /command palette/i })).toBeInTheDocument()
  })

  it('leaves Ctrl+K alone while the caret is in a text box', async () => {
    // The message composer binds its own shortcuts and the browser binds others; a global
    // hotkey that fires mid-sentence is the defect here.
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByLabelText('Composer'))
    await user.keyboard('{Control>}k{/Control}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('filters as you type and activates the highlighted entry with Enter', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    await user.type(screen.getByRole('combobox'), 'boa')
    expect(optionNames()).toEqual(['Board'])
    await user.keyboard('{Enter}')
    expect(await screen.findByTestId('location')).toHaveTextContent('/app/board')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('moves the highlight with the arrow keys', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    expect(screen.getByRole('option', { name: 'Inbox' })).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowDown}{ArrowDown}')
    expect(screen.getByRole('option', { name: 'Alerts' })).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowUp}')
    expect(screen.getByRole('option', { name: 'Board' })).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{Enter}')
    expect(await screen.findByTestId('location')).toHaveTextContent('/app/board')
  })

  it('offers an agent only what an agent can reach, and no admin sections at all', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    expect(optionNames()).toEqual([
      'Inbox',
      'Board',
      'Alerts',
      'Messages',
      'Log',
      'Switch to light theme',
      'Sign out',
    ])
  })

  it('lists the admin sub-sections to a role with manage_admin', async () => {
    const user = userEvent.setup()
    mount({ role: 'admin' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    expect(optionNames()).toContain('Quick replies')
    expect(optionNames()).toContain('Property settings')
    await user.type(screen.getByRole('combobox'), 'quick')
    await user.keyboard('{Enter}')
    expect(await screen.findByTestId('location')).toHaveTextContent('/app/admin/quick-replies')
  })

  it('hides the Board from corporate, which holds neither work-order capability', async () => {
    // corporate has manage_admin but not reply, create_work_order or close_work_order
    // (server/app/auth/permissions.py) — so it sees Admin and the Inbox but never the Board.
    const user = userEvent.setup()
    mount({ role: 'corporate' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    expect(optionNames()).toContain('Inbox')
    expect(optionNames()).toContain('Analytics')
    expect(optionNames()).not.toContain('Board')
  })

  it('offers no property entries to a single-property user', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    expect(optionNames().some((n) => n?.startsWith('Switch to Harbourview'))).toBe(false)
  })

  it('switches property and lands on the target role’s landing screen', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent', withSecondProperty: true, secondRole: 'admin' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    await user.type(screen.getByRole('combobox'), 'Lakeside')
    await user.keyboard('{Enter}')
    expect(localStorage.getItem('activePropertyId')).toBe('prop-b')
    // Admin at Lakeside, agent at Harbourview: the landing screen follows the *target*
    // membership's role, exactly as the rail's switcher does.
    expect(await screen.findByTestId('location')).toHaveTextContent('/app/analytics')
  })

  it('toggles the theme from the palette', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    await user.type(screen.getByRole('combobox'), 'theme')
    await user.keyboard('{Enter}')
    await vi.waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
  })

  it('makes no server call when it opens or filters (D63)', async () => {
    // It is a NAVIGATION palette: the only `q=` parameter on the whole server is
    // quick_replies.py:16, and there is no conversation, guest or work-order search endpoint.
    // Without this, a future `q=` call added here would go green.
    const user = userEvent.setup()
    mount({ role: 'admin', withSecondProperty: true })
    await screen.findByRole('button', { name: /jump to a screen/i })
    vi.mocked(fetch).mockClear()

    await user.click(screen.getByRole('button', { name: /jump to a screen/i }))
    await user.type(screen.getByRole('combobox'), 'prop')
    await user.keyboard('{ArrowDown}')

    expect(fetch).not.toHaveBeenCalled()
  })

  it('owns its options directly, with no listitem between listbox and option', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    const listbox = screen.getByRole('listbox')
    // `listitem` is not an allowed child of `listbox`; a screen reader that honours the
    // ownership rules then mis-counts or skips options.
    expect(within(listbox).queryAllByRole('listitem')).toHaveLength(0)
    expect(within(listbox).getAllByRole('option').length).toBe(optionNames().length)
  })

  it('says so rather than showing an empty list when nothing matches', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    await user.type(screen.getByRole('combobox'), 'zzz')
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    expect(screen.getByText('Nothing matches that.')).toBeInTheDocument()
  })

  it('keeps Tab inside the dialog while it is open', async () => {
    const user = userEvent.setup()
    mount({ role: 'agent' })
    await user.click(await screen.findByRole('button', { name: /jump to a screen/i }))
    const box = screen.getByRole('combobox')
    await user.tab()
    expect(box).toHaveFocus()
  })
})
