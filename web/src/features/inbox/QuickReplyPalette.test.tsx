import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { aQuickReply } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { SessionProvider } from '../../auth/SessionContext'
import { QuickReplyPalette, filterQuickReplies } from './QuickReplyPalette'

const REPLIES = [
  aQuickReply({ id: 'q1', shortcut: '/wifi', title: 'WiFi details', body: 'The network is Harbourview-Guest.' }),
  aQuickReply({ id: 'q2', shortcut: '/checkout', title: 'Checkout time', body: 'Checkout is 11 AM.' }),
  aQuickReply({ id: 'q3', shortcut: '/late', title: 'Late checkout granted', body: 'Your checkout is extended to 2 PM.' }),
  aQuickReply({ id: 'q4', shortcut: '/towels', title: 'Towels on the way', body: 'Fresh towels are on their way.' }),
]

describe('filterQuickReplies', () => {
  it('returns everything for an empty term', () => {
    expect(filterQuickReplies(REPLIES, '')).toHaveLength(4)
  })

  it('matches a shortcut prefix', () => {
    expect(filterQuickReplies(REPLIES, 'wi').map((r) => r.id)).toEqual(['q1'])
  })

  it('matches a shortcut prefix with the slash typed', () => {
    expect(filterQuickReplies(REPLIES, '/wi').map((r) => r.id)).toEqual(['q1'])
  })

  it('matches a word in the body, not only the shortcut (§5.3)', () => {
    expect(filterQuickReplies(REPLIES, 'harbourview-guest').map((r) => r.id)).toEqual(['q1'])
  })

  it('matches a word in the title', () => {
    expect(filterQuickReplies(REPLIES, 'granted').map((r) => r.id)).toEqual(['q3'])
  })

  it('is case-insensitive', () => {
    expect(filterQuickReplies(REPLIES, 'WIFI').map((r) => r.id)).toEqual(['q1'])
  })

  it('sorts shortcut-prefix matches before body matches', () => {
    // '/late' matches by shortcut; '/checkout' matches 'late' nowhere, but
    // 'Late checkout granted' body mentions checkout — so both can match 'checkout'.
    const ids = filterQuickReplies(REPLIES, 'checkout').map((r) => r.id)
    expect(ids[0]).toBe('q2')
    expect(ids).toContain('q3')
  })

  it('returns nothing when nothing matches', () => {
    expect(filterQuickReplies(REPLIES, 'helicopter')).toEqual([])
  })

  it('ignores inactive replies — a paused reply must not be offered', () => {
    const withPaused = [...REPLIES, aQuickReply({ id: 'q5', shortcut: '/shuttle', active: false })]
    expect(filterQuickReplies(withPaused, 'shuttle')).toEqual([])
  })
})

describe('QuickReplyPalette', () => {
  function mount(onPick = vi.fn()) {
    renderWithProviders(
      <SessionProvider>
        <QuickReplyPalette replies={REPLIES} term="" onPick={onPick} onClose={vi.fn()} />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    return onPick
  }

  it('lists each reply with its shortcut and title', async () => {
    mount()
    expect(await screen.findByText('/wifi')).toBeInTheDocument()
    expect(screen.getByText('WiFi details')).toBeInTheDocument()
  })

  it('selects the first item by default', async () => {
    mount()
    expect(await screen.findByTestId('qr-q1')).toHaveAttribute('aria-selected', 'true')
  })

  it('moves the selection with the arrow keys', async () => {
    mount()
    await screen.findByTestId('qr-q1')
    await userEvent.keyboard('{ArrowDown}')
    expect(screen.getByTestId('qr-q2')).toHaveAttribute('aria-selected', 'true')
    await userEvent.keyboard('{ArrowUp}')
    expect(screen.getByTestId('qr-q1')).toHaveAttribute('aria-selected', 'true')
  })

  it('does not move above the first or below the last item', async () => {
    mount()
    await screen.findByTestId('qr-q1')
    await userEvent.keyboard('{ArrowUp}')
    expect(screen.getByTestId('qr-q1')).toHaveAttribute('aria-selected', 'true')
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}')
    expect(screen.getByTestId('qr-q4')).toHaveAttribute('aria-selected', 'true')
  })

  it('picks the selected reply on Enter', async () => {
    const onPick = mount()
    await screen.findByTestId('qr-q1')
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 'q2' }))
  })

  it('picks on click', async () => {
    const onPick = mount()
    await userEvent.click(await screen.findByTestId('qr-q3'))
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 'q3' }))
  })

  // Fix-round: a term matching nothing renders no visible list, but the component was
  // still globally intercepting ArrowUp/ArrowDown/Escape — an agent typing a `/`-prefixed
  // draft with no match would find arrow-key cursor movement silently broken, with nothing
  // on screen to explain why.
  it('does not intercept arrow keys when there are no matches', async () => {
    renderWithProviders(
      <SessionProvider>
        <QuickReplyPalette replies={REPLIES} term="helicopter" onPick={vi.fn()} onClose={vi.fn()} />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    const event = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true })
    document.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
  })
})
