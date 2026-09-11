import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role, StayOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { aConversationDetail, aDepartment, aGuest, aStaffUser, aStay } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { GuestPanel } from './GuestPanel'
import { aWorkOrder, aDraftPrompt, aNote } from '../../test/factories'

/** GET /guests/<id> — the only call this panel makes on its own. */
function serveStays(stays: StayOut[]) {
  vi.mocked(fetch).mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ guest: aGuest(), stays, conversationIds: ['c-1'] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

/** Also serves what the "+ New" work-order modal asks for once opened. */
function serveWithWorkOrderModal() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('prefill')
      ? {
          title: 'AC not cooling', description: 'The AC in 412 is not working.',
          type: 'maintenance', priority: 'urgent', locationType: 'room', locationRef: '412',
          departmentId: 'dept-eng', guestName: 'Sarah Chen', sourceConversationId: 'c-1',
          sourceMessageId: 'm-1',
        }
      : url.includes('/departments')
        ? [aDepartment()]
        : url.includes('/users')
          ? [aStaffUser()]
          : url.includes('/guests/')
            ? { guest: aGuest(), stays: [], conversationIds: ['c-1'] }
            : []
    return Promise.resolve(
      new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
  })
}

function mount(detail = aConversationDetail(), role: Role = 'agent') {
  return renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <GuestPanel conversation={detail} />
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role }), route: '/app/inbox/c-1' },
  )
}

describe('GuestPanel', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serveStays([])
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the guest identity and phone in mono', async () => {
    mount()
    expect(await screen.findByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText('+15551234567').className).toContain('font-mono')
  })

  it('shows the stay: room, type, dates and stay count', async () => {
    mount()
    expect(await screen.findByText('412 · King')).toBeInTheDocument()
    expect(screen.getByText(/2026-09-09/)).toBeInTheDocument()
    expect(screen.getByText(/4th stay/i)).toBeInTheDocument()
  })

  it('shows consent status as a green chip when opted in', async () => {
    mount()
    const chip = await screen.findByText('Opted in')
    expect(chip.className).toContain('okText')
  })

  it('shows consent status as a red chip when opted out', async () => {
    mount(aConversationDetail({ guest: aGuest({ smsConsentStatus: 'opted_out' }) }))
    const chip = await screen.findByText('Opted out')
    expect(chip.className).toContain('dangerText')
  })

  it('lists open work orders with a link to each', async () => {
    mount(aConversationDetail({ workOrders: [aWorkOrder({ id: 'w-204', title: 'AC not cooling' })] }))
    const link = await screen.findByRole('link', { name: /AC not cooling/ })
    expect(link).toHaveAttribute('href', '/app/work-orders/w-204')
  })

  it('reports pending draft prompts', async () => {
    mount(aConversationDetail({ draftPrompts: [aDraftPrompt()] }))
    expect(await screen.findByText(/1 pending prompt/i)).toBeInTheDocument()
  })

  it('lists recent notes', async () => {
    mount(aConversationDetail({ notes: [aNote({ body: 'Guest is Gold, 4th stay.' })] }))
    expect(await screen.findByText('Guest is Gold, 4th stay.')).toBeInTheDocument()
  })

  it('handles a guest with no stay without crashing', async () => {
    mount(aConversationDetail({ stay: null, guest: aGuest({ firstName: null, lastName: null }) }))
    expect(await screen.findByText('No stay on file')).toBeInTheDocument()
  })

  // R1.2 — `StayOut` carries no rating and no conversation count, so the mockup's
  // "1 conv" and "5★" are not rendered: month, nights and status are what exist.
  it('lists previous stays as month, nights and status', async () => {
    serveStays([
      aStay(),
      aStay({ id: 's-0', arrivalDate: '2026-06-14', departureDate: '2026-06-16', status: 'checked_out' }),
    ])
    mount()
    const line = await screen.findByText('JUN 2026 · 2N · CHECKED OUT')
    expect(line.className).toContain('font-mono')
  })

  it('excludes the current stay, which has its own section', async () => {
    serveStays([aStay()])
    mount()
    expect(await screen.findByText('Previous stays')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Previous stays').parentElement).toHaveTextContent('None'))
  })

  it('says None for a first-time guest', async () => {
    serveStays([])
    mount()
    await waitFor(() => expect(screen.getByText('Previous stays').parentElement).toHaveTextContent('None'))
  })

  // Fix round 1: a failed lookup rendered "None", which is the answer for a first-time
  // guest — the opposite of "we do not know".
  it('says so when the stay history cannot be loaded, rather than None', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'SERVER_ERROR', message: 'boom' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    mount()
    expect(await screen.findByText('Stay history unavailable')).toBeInTheDocument()
    expect(screen.getByText('Previous stays').parentElement).not.toHaveTextContent('None')
  })

  // GET /guests/<id> is gated server-side on view_all_conversations, which dept_staff
  // lacks — showing the section would only produce a 403.
  it('hides the section, and asks for nothing, for a role without view_all_conversations', async () => {
    mount(aConversationDetail(), 'dept_staff')
    await screen.findByText('Sarah Chen')
    expect(screen.queryByText('Previous stays')).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/guests/'))).toBe(false)
  })

  // M11: the guest panel's Work orders section had a list but no way to raise one.
  it('offers + New to a role that can create work orders', async () => {
    mount(aConversationDetail(), 'agent')
    expect(await screen.findByRole('button', { name: '+ New' })).toBeInTheDocument()
  })

  it('hides + New from corporate, which lacks create_work_order', async () => {
    mount(aConversationDetail(), 'corporate')
    await screen.findByText('Sarah Chen')
    expect(screen.queryByRole('button', { name: '+ New' })).not.toBeInTheDocument()
  })

  it('opens the create-work-order modal, prefilled from this conversation', async () => {
    serveWithWorkOrderModal()
    mount(aConversationDetail({ id: 'c-1' }), 'agent')
    await userEvent.click(await screen.findByRole('button', { name: '+ New' }))
    expect(await screen.findByRole('dialog', { name: 'Create work order' })).toBeInTheDocument()
    // Prefilled from THIS conversation, the same path the composer's own button uses.
    expect(await screen.findByDisplayValue('AC not cooling')).toBeInTheDocument()
    expect(
      vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('prefill') && String(u).includes('c-1')),
    ).toBe(true)
  })
})
