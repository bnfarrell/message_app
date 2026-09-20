import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LogEntryOut, Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { LogEntryCard } from './LogEntryCard'
import { tokenFor } from './MentionInput'

const ANA_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
const PRIYA_ID = 'cccccccc-cccc-cccc-cccc-cccccccccccc'

const BASE: LogEntryOut = {
  id: 'log-1',
  authorUserId: 'u-eli',
  authorName: 'Eli Vance',
  body: 'Checked the boiler room.',
  createdAt: '2026-09-19T12:00:00Z',
  pinned: false,
  requiresAck: false,
  ackExpectedCount: 0,
  ackedByMe: false,
  canAck: false,
  shift: 'am',
}

function serve() {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify({ ...BASE, pinned: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function mount(entry: LogEntryOut, role: Role = 'agent') {
  return renderWithProviders(
    <SessionProvider>
      <LogEntryCard entry={entry} />
    </SessionProvider>,
    { session: sessionFixture({ role }) },
  )
}

function pinCalls() {
  return vi.mocked(fetch).mock.calls.filter(([input]) => String(input).includes('/pin'))
}

describe('LogEntryCard', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders author name, shift badge, and department tag', () => {
    mount({ ...BASE, departmentName: 'Engineering' })
    expect(screen.getByText('Eli Vance')).toBeInTheDocument()
    expect(screen.getByText('AM')).toBeInTheDocument()
    expect(screen.getByText('Engineering')).toBeInTheDocument()
  })

  it('renders a mention token as the display name only, never the raw token', () => {
    const token = tokenFor({ type: 'user', id: ANA_ID, displayName: 'Ana Marquez' })
    mount({ ...BASE, body: `Please see ${token} about this.` })
    expect(screen.getByText('Ana Marquez')).toBeInTheDocument()
    expect(screen.queryByText(/\]\(user:/)).toBeNull()
  })

  it('parses mentions correctly across two entries rendered in the same pass', () => {
    const tokenA = tokenFor({ type: 'user', id: ANA_ID, displayName: 'Ana Marquez' })
    const tokenB = tokenFor({ type: 'user', id: PRIYA_ID, displayName: 'Priya Shah' })
    renderWithProviders(
      <SessionProvider>
        <LogEntryCard entry={{ ...BASE, id: 'log-1', body: `See ${tokenA}` }} />
        <LogEntryCard entry={{ ...BASE, id: 'log-2', body: `See ${tokenB}` }} />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    expect(screen.getByText('Ana Marquez')).toBeInTheDocument()
    expect(screen.getByText('Priya Shah')).toBeInTheDocument()
    expect(screen.queryByText(/\]\(user:/)).toBeNull()
  })

  it('renders an img when photoUrl is set', () => {
    mount({ ...BASE, photoUrl: 'https://example.test/photo.jpg' })
    expect(screen.getByRole('img')).toBeInTheDocument()
  })

  it('renders no img when photoUrl is null', () => {
    mount({ ...BASE, photoUrl: null })
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('shows no Pin control without the pin_log_entry capability', () => {
    mount(BASE, 'agent')
    expect(screen.queryByRole('button', { name: /pin/i })).not.toBeInTheDocument()
  })

  it('shows a Pin button that POSTs when the viewer can pin', async () => {
    mount(BASE, 'manager')
    const button = screen.getByRole('button', { name: 'Pin' })
    await userEvent.click(button)
    expect(pinCalls()).toHaveLength(1)
    expect(pinCalls()[0]?.[1]?.method).toBe('POST')
  })

  it('shows Unpin and DELETEs when the entry is already pinned', async () => {
    mount({ ...BASE, pinned: true }, 'manager')
    const button = screen.getByRole('button', { name: 'Unpin' })
    await userEvent.click(button)
    expect(pinCalls()).toHaveLength(1)
    expect(pinCalls()[0]?.[1]?.method).toBe('DELETE')
  })

  it('renders a mention whose display name contains HTML as literal text', () => {
    const token = tokenFor({ type: 'user', id: ANA_ID, displayName: '<b>x</b>' })
    mount({ ...BASE, body: `Hello ${token}` })
    expect(screen.getByText('<b>x</b>')).toBeInTheDocument()
    expect(document.querySelector('b')).toBeNull()
  })
})
