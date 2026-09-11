import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { NoteOut } from '../../api/types'
import { RealtimeProvider } from '../../api/ws'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { aConversationDetail, aGuest, aMessage, aNote, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ConversationView } from './ConversationView'

function serve(detail: unknown) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/users')
      ? [aStaffUser(), aStaffUser({ id: 'u-marcus', firstName: 'Marcus', lastName: 'Reyes' })]
      : url.includes('/departments')
        ? []
        : detail
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <RealtimeProvider>
          <ConversationView conversationId="c-1" />
        </RealtimeProvider>
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: '/app/inbox/c-1' },
  )
}

describe('ConversationView', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.stubGlobal(
      'WebSocket',
      class {
        static OPEN = 1
        onopen: (() => void) | null = null
        onmessage: unknown = null
        onclose: unknown = null
        readyState = 1
        send() {}
        close() {}
      } as unknown as typeof WebSocket,
    )
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the room, guest and stay chips in the header', async () => {
    serve(aConversationDetail())
    mount()
    expect(await screen.findByText('412')).toBeInTheDocument()
    // The guest panel legitimately repeats the name and tier chips (§5.2), so scope to the header (§5.3).
    const header = screen.getByRole('banner')
    expect(within(header).getByText('Sarah Chen')).toBeInTheDocument()
    expect(within(header).getByText(/GOLD/i)).toBeInTheDocument()
    expect(within(header).getByText(/4TH STAY/i)).toBeInTheDocument()
  })

  it('interleaves notes with messages in time order', async () => {
    serve(
      aConversationDetail({
        messages: [
          aMessage({ id: 'm-1', body: 'first', sentAt: '2026-09-10T18:41:00Z' }),
          aMessage({ id: 'm-2', body: 'third', sentAt: '2026-09-10T18:45:00Z' }),
        ],
        notes: [aNote({ id: 'n-1', body: 'second', createdAt: '2026-09-10T18:43:00Z' })],
      }),
    )
    mount()
    await screen.findByText('first')
    const order = screen.getAllByTestId(/^(bubble|note)$/).map((el) => el.textContent)
    expect(order.join('|')).toMatch(/first.*second.*third/)
  })

  it('renders an internal note distinctly and labels it Internal', async () => {
    serve(aConversationDetail({ notes: [aNote({ body: 'Guest is Gold.' })] }))
    mount()
    const note = await screen.findByTestId('note')
    expect(note.className).toContain('bg-noteBg')
    expect(screen.getByText('Internal')).toBeInTheDocument()
  })

  it('warns but does not disable the thread for an opted-out guest (§5.3)', async () => {
    serve(aConversationDetail({ guest: aGuest({ smsConsentStatus: 'opted_out' }) }))
    mount()
    // Both the header chip and the guest panel's consent section show it (§5.2/§5.3) — any is proof of the warning.
    const warnings = await screen.findAllByText(/opted out/i)
    expect(warnings.length).toBeGreaterThan(0)
    // "does not disable the thread" is half the title and was never asserted.
    expect(screen.getByRole('textbox')).toBeEnabled()
  })

  // R1.1: nothing in the product could create a note before this. The whole loop is under
  // test — POST /notes, then the invalidated detail query putting it in the thread.
  it('writes an internal note and shows it in the thread', async () => {
    let notes: NoteOut[] = []
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/notes') && init?.method === 'POST') {
        const sent = JSON.parse(String(init.body)) as { body: string }
        const created = aNote({ id: 'n-new', body: sent.body })
        notes = [created]
        return Promise.resolve(
          new Response(JSON.stringify(created), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      // Everything but the conversation detail itself is a list route here.
      const body = url.includes('/users')
        ? [aStaffUser()]
        : url.includes('/conversations/c-1')
          ? aConversationDetail({ notes })
          : []
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      )
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Note' }))
    await userEvent.type(screen.getByRole('textbox'), 'Raised WO #204 to Engineering.')
    await userEvent.click(screen.getByRole('button', { name: /add note/i }))
    expect(await screen.findByTestId('note')).toHaveTextContent('Raised WO #204 to Engineering.')
  })

  it('shows an error state when the conversation cannot be loaded', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Conversation not found' } }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    mount()
    expect(await screen.findByText('Conversation not found')).toBeInTheDocument()
  })
})
