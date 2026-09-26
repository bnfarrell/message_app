import { screen, within } from '@testing-library/react'
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

  it('renders the work order and conversation links with correct hrefs, and omits them when unset', () => {
    const WORK_ORDER_ID = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
    const CONVERSATION_ID = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
    mount({ ...BASE, linkedWorkOrderId: WORK_ORDER_ID, linkedConversationId: CONVERSATION_ID })
    expect(screen.getByRole('link', { name: 'View work order' })).toHaveAttribute(
      'href',
      `/app/work-orders/${WORK_ORDER_ID}`,
    )
    expect(screen.getByRole('link', { name: 'View conversation' })).toHaveAttribute(
      'href',
      `/app/inbox/${CONVERSATION_ID}`,
    )
  })

  it('renders neither link when linkedWorkOrderId and linkedConversationId are null', () => {
    mount({ ...BASE, linkedWorkOrderId: null, linkedConversationId: null })
    expect(screen.queryByRole('link', { name: 'View work order' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'View conversation' })).not.toBeInTheDocument()
  })

  it('renders a mention whose display name contains HTML as literal text', () => {
    const token = tokenFor({ type: 'user', id: ANA_ID, displayName: '<b>x</b>' })
    mount({ ...BASE, body: `Hello ${token}` })
    expect(screen.getByText('<b>x</b>')).toBeInTheDocument()
    expect(document.querySelector('b')).toBeNull()
  })

  describe('a templated post', () => {
    const TEMPLATED: LogEntryOut = {
      ...BASE,
      body: 'Arrivals actual: 38\nOccupancy: 87.5%\n\nQuiet night.',
      template: { id: 't-night', name: 'Night Audit' },
      fieldValues: [
        { fieldId: 'f-arr', label: 'Arrivals actual', fieldType: 'integer', numberValue: 38 },
        { fieldId: 'f-occ', label: 'Occupancy', fieldType: 'percent', numberValue: 87.5 },
      ],
      notes: 'Quiet night.',
    }

    it('shows the template tag and a label/value table with percent formatting', () => {
      mount(TEMPLATED)
      expect(screen.getByText('Night Audit')).toBeInTheDocument()
      const table = screen.getByText('Arrivals actual').closest('dl')!
      expect(table).not.toBeNull()
      expect(within(table).getByText('38')).toBeInTheDocument()
      expect(within(table).getByText('87.5%')).toBeInTheDocument()
    })

    it('renders the notes under the table, never the generated summary', () => {
      mount(TEMPLATED)
      expect(screen.getByText('Quiet night.')).toBeInTheDocument()
      expect(screen.queryByText(/Arrivals actual: 38/)).toBeNull()
    })

    it('renders no body paragraph at all when there are no notes', () => {
      mount({ ...TEMPLATED, body: 'Arrivals actual: 38\nOccupancy: 87.5%', notes: null })
      expect(screen.queryByText(/Arrivals actual:/)).toBeNull()
      expect(screen.getByText('87.5%')).toBeInTheDocument()
    })
  })
})
