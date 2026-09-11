import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RealtimeProvider } from '../../api/ws'
import { SessionProvider } from '../../auth/SessionContext'
import { aAsset, aConversationDetail, aGuest, aMessage, aQuickReply } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { Composer } from './Composer'

function routes(overrides: Record<string, unknown> = {}) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const table: Record<string, unknown> = {
      'quick-replies': [aQuickReply()],
      assets: [aAsset()],
      departments: [],
      users: [],
      ...overrides,
    }
    if (url.includes('/messages') && method === 'POST') {
      const body = JSON.parse(String(init?.body ?? '{}')) as { body: string }
      return Promise.resolve(
        new Response(
          JSON.stringify(
            (table['send'] as unknown) ??
              aMessage({ id: 'm-real', direction: 'outbound', authorType: 'staff', body: body.body, deliveryStatus: 'queued' }),
          ),
          { status: 201, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    }
    // '/render' is checked before the generic table lookup below: its URL
    // (quick-replies/<id>/render) also contains 'quick-replies', which would otherwise
    // match first and shadow this branch's override.
    if (url.includes('/render') && method === 'POST') {
      return Promise.resolve(
        new Response(JSON.stringify(table['render'] ?? { body: '', characters: 0, segments: 0 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const key = Object.keys(table).find((k) => url.includes(k))
    return Promise.resolve(
      new Response(JSON.stringify(key ? table[key] : aConversationDetail()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(detail = aConversationDetail()) {
  return renderWithProviders(
    <SessionProvider>
      <RealtimeProvider>
        <Composer conversationId={detail.id} conversation={detail} />
      </RealtimeProvider>
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: `/app/inbox/${detail.id}` },
  )
}

describe('Composer', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.stubGlobal(
      'WebSocket',
      class {
        static OPEN = 1
        readyState = 1
        onopen: (() => void) | null = null
        onmessage: unknown = null
        onclose: unknown = null
        send() {}
        close() {}
      } as unknown as typeof WebSocket,
    )
    routes()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows no counter for an empty draft', async () => {
    mount()
    await screen.findByRole('textbox')
    expect(screen.queryByTestId('segment-counter')).not.toBeInTheDocument()
  })

  it('counts characters and segments as you type', async () => {
    mount()
    await userEvent.type(await screen.findByRole('textbox'), 'Hello')
    expect(screen.getByTestId('segment-counter')).toHaveTextContent('5 chars · 1 segment')
  })

  it('pluralises segments and warns at two', async () => {
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.click(box)
    await userEvent.paste('a'.repeat(161))
    const counter = screen.getByTestId('segment-counter')
    expect(counter).toHaveTextContent('161 chars · 2 segments')
    expect(counter.className).toContain('warnText')
  })

  it('turns red past four segments, where cost stops being incidental', async () => {
    mount()
    await userEvent.click(await screen.findByRole('textbox'))
    await userEvent.paste('a'.repeat(800))
    expect(screen.getByTestId('segment-counter').className).toContain('dangerText')
  })

  it('counts a non-GSM draft against the UCS-2 limit', async () => {
    mount()
    await userEvent.click(await screen.findByRole('textbox'))
    await userEvent.paste('日'.repeat(71))
    expect(screen.getByTestId('segment-counter')).toHaveTextContent('71 chars · 2 segments')
  })

  it('sends on Ctrl+Enter and clears the box', async () => {
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'On our way')
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    await waitFor(() => expect(box).toHaveValue(''))
    const sent = vi.mocked(fetch).mock.calls.find(([u, i]) => String(u).includes('/messages') && i?.method === 'POST')
    expect(JSON.parse(String(sent![1]!.body))).toMatchObject({ body: 'On our way' })
  })

  it('does not send on a plain Enter — that inserts a newline', async () => {
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'Line one{Enter}Line two')
    expect(box).toHaveValue('Line one\nLine two')
    expect(
      vi.mocked(fetch).mock.calls.some(([u, i]) => String(u).includes('/messages') && i?.method === 'POST'),
    ).toBe(false)
  })

  it('does not send an empty or whitespace-only draft', async () => {
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, '   ')
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    expect(
      vi.mocked(fetch).mock.calls.some(([u, i]) => String(u).includes('/messages') && i?.method === 'POST'),
    ).toBe(false)
  })

  it('opens the palette on / in an empty box', async () => {
    mount()
    await userEvent.type(await screen.findByRole('textbox'), '/')
    expect(await screen.findByTestId('qr-q-1')).toBeInTheDocument()
  })

  it('does not open the palette on a / mid-sentence', async () => {
    mount()
    await userEvent.type(await screen.findByRole('textbox'), 'either/or')
    expect(screen.queryByTestId('qr-q-1')).not.toBeInTheDocument()
  })

  it('closes the palette on Escape and keeps the typed text', async () => {
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, '/wi')
    await screen.findByTestId('qr-q-1')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByTestId('qr-q-1')).not.toBeInTheDocument()
    expect(box).toHaveValue('/wi')
  })

  it('inserts the server-rendered body, not the raw template', async () => {
    routes({ render: { body: 'Hi Sarah — the network is Harbourview-Guest.', characters: 44, segments: 1 } })
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, '/wifi')
    await userEvent.keyboard('{Enter}')
    await waitFor(() => expect(box).toHaveValue('Hi Sarah — the network is Harbourview-Guest.'))
    // jest-dom's toHaveValue in this version does a strict equality check and does not
    // evaluate asymmetric matchers, so the substring check is made directly on .value.
    expect((box as HTMLTextAreaElement).value).not.toContain('{{')
  })

  it('appends a short link when an asset is picked', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /attach/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /WiFi card/ }))
    await waitFor(() =>
      expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toContain('/a/wifi1'),
    )
  })

  it('shows the consent warning but stays enabled for an opted-out guest (§5.3)', async () => {
    mount(aConversationDetail({ guest: aGuest({ smsConsentStatus: 'opted_out' }) }))
    expect(await screen.findByText(/opted out of SMS/i)).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeEnabled()
  })

  it('restores the draft and shows the server reason when a send is rejected', async () => {
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'Please reply')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ error: { code: 'CONSENT_OPTED_OUT', message: 'Guest has opted out of SMS' } }),
        { status: 422, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Guest has opted out of SMS')
    // The text must come back — the agent should not have to retype it.
    await waitFor(() => expect(box).toHaveValue('Please reply'))
  })

  it('reports composing presence on focus and viewing on blur (§6.1)', async () => {
    const frames: string[] = []
    vi.stubGlobal(
      'WebSocket',
      class {
        static OPEN = 1
        readyState = 1
        onopen: (() => void) | null = null
        onmessage: unknown = null
        onclose: unknown = null
        send(data: string) {
          frames.push(data)
        }
        close() {}
      } as unknown as typeof WebSocket,
    )
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.click(box)
    await waitFor(() => expect(frames.some((f) => f.includes('"state":"composing"'))).toBe(true))
    await userEvent.tab()
    await waitFor(() => expect(frames.some((f) => f.includes('"state":"viewing"'))).toBe(true))
  })

  // Added per the Task 14 dispatch: corporate holds view_all_conversations and add_note
  // but not reply, so it must get a read-only thread rather than a composer the server
  // would reject a send from.
  it('renders nothing for a role without the reply capability', async () => {
    const detail = aConversationDetail()
    renderWithProviders(
      <SessionProvider>
        <RealtimeProvider>
          <Composer conversationId={detail.id} conversation={detail} />
        </RealtimeProvider>
      </SessionProvider>,
      { session: sessionFixture({ role: 'corporate' }), route: `/app/inbox/${detail.id}` },
    )
    await waitFor(() => expect(screen.queryByRole('textbox')).not.toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument()
  })
})
