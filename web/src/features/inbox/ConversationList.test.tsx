import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversation, aGuest, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ConversationList } from './ConversationList'

function respondWith(rows: unknown[], staff: unknown[] = [aStaffUser()]) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/users') ? staff : url.includes('/departments') ? [] : rows
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(selectedId?: string) {
  return renderWithProviders(
    <SessionProvider>
      <ConversationList filter="all" selectedId={selectedId} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: '/app/inbox' },
  )
}

describe('ConversationList', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.stubGlobal('WebSocket', class { close() {} } as unknown as typeof WebSocket)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a row per conversation with room, guest and preview', async () => {
    respondWith([aConversation()])
    mount()
    expect(await screen.findByText('412')).toBeInTheDocument()
    expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText(/The AC in our room/)).toBeInTheDocument()
  })

  it('preserves the server order and does not re-sort', async () => {
    respondWith([
      aConversation({ id: 'c-1', roomNumber: '412', lastGuestMessageAt: '2026-09-10T18:41:00Z' }),
      aConversation({ id: 'c-2', roomNumber: '118', lastGuestMessageAt: '2026-09-10T17:00:00Z' }),
    ])
    mount()
    await screen.findByText('412')
    const rooms = screen.getAllByTestId('row-room').map((el) => el.textContent)
    expect(rooms).toEqual(['412', '118'])
  })

  it('prefixes an answered conversation with You:', async () => {
    respondWith([
      aConversation({
        unanswered: false,
        lastStaffMessageAt: '2026-09-10T18:50:00Z',
        lastMessagePreview: 'Your car is at the valet stand now.',
      }),
    ])
    mount()
    expect(await screen.findByText(/^You: Your car is at the valet/)).toBeInTheDocument()
  })

  it('shows Unassigned when nobody owns it', async () => {
    respondWith([aConversation({ assignedUserId: null, assignedDepartmentId: null })])
    mount()
    expect(await screen.findByText('Unassigned')).toBeInTheDocument()
  })

  it('shows the assignee initials when someone does', async () => {
    respondWith([aConversation({ assignedUserId: 'u-ava' })])
    mount()
    expect(await screen.findByTitle('Ava Nolan')).toBeInTheDocument()
  })

  it('marks a guest with no stay as New', async () => {
    respondWith([
      aConversation({
        roomNumber: null,
        guest: aGuest({ firstName: null, lastName: null, phoneE164: '+15550142290' }),
      }),
    ])
    mount()
    expect(await screen.findByText('New')).toBeInTheDocument()
    expect(screen.getByText('+15550142290')).toBeInTheDocument()
  })

  it('flags an opted-out guest in red (§5.3)', async () => {
    respondWith([aConversation({ guest: aGuest({ smsConsentStatus: 'opted_out' }) })])
    mount()
    const chip = await screen.findByText(/opted out/i)
    expect(chip.className).toContain('dangerText')
  })

  it('renders an SLA chip for an unanswered conversation and done for an answered one', async () => {
    respondWith([
      aConversation({ id: 'c-1', unanswered: true }),
      aConversation({ id: 'c-2', roomNumber: '205', unanswered: false }),
    ])
    mount()
    expect(await screen.findByText('done')).toBeInTheDocument()
  })

  it('marks the selected row', async () => {
    respondWith([aConversation({ id: 'c-1' })])
    mount('c-1')
    expect(await screen.findByRole('link', { name: /Sarah Chen/ })).toHaveAttribute(
      'aria-current',
      'true',
    )
  })

  it('shows an empty state rather than a blank column', async () => {
    respondWith([])
    mount()
    expect(await screen.findByText(/nothing waiting/i)).toBeInTheDocument()
  })

  it('shows the error message when the list fails', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'FORBIDDEN', message: 'Not your property' } }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    mount()
    expect(await screen.findByText('Not your property')).toBeInTheDocument()
  })
})
