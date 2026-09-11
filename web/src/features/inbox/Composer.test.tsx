import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RealtimeProvider } from '../../api/ws'
import type { Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { aAsset, aConversationDetail, aGuest, aMessage, aNote, aQuickReply } from '../../test/factories'
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
    if (url.includes('/notes') && method === 'POST') {
      const body = JSON.parse(String(init?.body ?? '{}')) as { body: string }
      return Promise.resolve(
        new Response(JSON.stringify(aNote({ id: 'n-real', body: body.body })), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
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

function mount(detail = aConversationDetail(), role: Role = 'agent') {
  return renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <RealtimeProvider>
          <Composer conversationId={detail.id} conversation={detail} />
        </RealtimeProvider>
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role }), route: `/app/inbox/${detail.id}` },
  )
}

const notePosts = () =>
  vi.mocked(fetch).mock.calls.filter(([u, i]) => String(u).includes('/notes') && i?.method === 'POST')

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

  // Fix-round: a failed render call left the raw /shortcut sitting in the box with no
  // feedback — an agent hitting Ctrl+Enter right after would send that literal text to
  // the guest. The box must clear and the error must surface instead.
  it('clears the raw shortcut and surfaces the error when rendering a quick reply fails', async () => {
    routes()
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, '/wifi')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ error: { code: 'SERVER_ERROR', message: 'Could not render the quick reply' } }),
        { status: 500, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not render the quick reply')
    await waitFor(() => expect(box).toHaveValue(''))
    // Nothing raw survives to be sent: an empty box fires no POST on Ctrl+Enter.
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    expect(
      vi.mocked(fetch).mock.calls.some(([u, i]) => String(u).includes('/messages') && i?.method === 'POST'),
    ).toBe(false)
  })

  // A render still in flight is the other half of the same risk: fast Ctrl+Enter must
  // not race ahead of it and send the raw shortcut before the interpolated body lands.
  it('does not send while a quick-reply render is still in flight', async () => {
    routes()
    let resolveRender: ((response: Response) => void) | null = null
    const baseImpl = vi.mocked(fetch).getMockImplementation()!
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/render') && (init?.method ?? 'GET') === 'POST') {
        return new Promise<Response>((resolve) => {
          resolveRender = resolve
        })
      }
      return baseImpl(input, init)
    })
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, '/wifi')
    await userEvent.keyboard('{Enter}')
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    expect(
      vi.mocked(fetch).mock.calls.some(([u, i]) => String(u).includes('/messages') && i?.method === 'POST'),
    ).toBe(false)
    resolveRender!(
      new Response(JSON.stringify({ body: 'Hi Sarah — the network is Harbourview-Guest.', characters: 44, segments: 1 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await waitFor(() => expect(box).toHaveValue('Hi Sarah — the network is Harbourview-Guest.'))
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

  // R1.1 supersedes the Task 14 expectation that corporate gets nothing at all: corporate
  // holds `add_note`, so it gets a note-only composer — and still no outbound send.
  it('offers a role without `reply` the note composer and no outbound send', async () => {
    mount(aConversationDetail(), 'corporate')
    expect(await screen.findByRole('textbox')).toHaveAttribute(
      'placeholder',
      'Internal note — not sent to the guest',
    )
    expect(screen.getByRole('button', { name: 'Note' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('button', { name: 'Reply' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^send$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /attach/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /quick/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /work order/i })).not.toBeInTheDocument()
  })

  it('posts a note through the notes endpoint, not the messages endpoint', async () => {
    mount(aConversationDetail(), 'corporate')
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'Raised WO #204 to Engineering, urgent.')
    await userEvent.click(screen.getByRole('button', { name: /add note/i }))
    await waitFor(() => expect(notePosts()).toHaveLength(1))
    expect(JSON.parse(String(notePosts()[0]![1]!.body))).toEqual({
      body: 'Raised WO #204 to Engineering, urgent.',
    })
    expect(
      vi.mocked(fetch).mock.calls.some(([u, i]) => String(u).includes('/messages') && i?.method === 'POST'),
    ).toBe(false)
    await waitFor(() => expect(box).toHaveValue(''))
  })

  // The toggle keys off `add_note`, never `reply` — gating it on `reply` is what left
  // corporate with nothing it could do anywhere in the inbox.
  it('shows the Reply/Note toggle to a role that holds both capabilities', async () => {
    mount()
    expect(await screen.findByRole('button', { name: 'Reply' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Note' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('drops the SMS-only affordances when switched to Note mode', async () => {
    mount()
    await userEvent.type(await screen.findByRole('textbox'), 'Hello there')
    expect(screen.getByTestId('segment-counter')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Note' }))
    expect(screen.queryByTestId('segment-counter')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /attach/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /quick/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /work order/i })).not.toBeInTheDocument()
  })

  it('does not open the quick-reply palette in Note mode', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Note' }))
    await userEvent.type(screen.getByRole('textbox'), '/wifi')
    expect(screen.queryByTestId('qr-q-1')).not.toBeInTheDocument()
  })

  // Consent governs outbound SMS, not internal notes: an opted-out guest must not stop
  // staff recording one.
  it('posts a note for an opted-out guest, and hides the SMS consent warning', async () => {
    mount(aConversationDetail({ guest: aGuest({ smsConsentStatus: 'opted_out' }) }))
    await userEvent.click(await screen.findByRole('button', { name: 'Note' }))
    expect(screen.queryByText(/opted out of SMS/i)).not.toBeInTheDocument()
    const box = screen.getByRole('textbox')
    expect(box).toBeEnabled()
    await userEvent.type(box, 'Guest opted out — call room 412 instead.')
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    await waitFor(() => expect(notePosts()).toHaveLength(1))
    expect(JSON.parse(String(notePosts()[0]![1]!.body))).toEqual({
      body: 'Guest opted out — call room 412 instead.',
    })
  })

  it('gives the note text back when the server rejects it', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Note' }))
    const box = screen.getByRole('textbox')
    await userEvent.type(box, 'A note')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'FORBIDDEN', message: 'Not allowed' } }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Not allowed')
    await waitFor(() => expect(box).toHaveValue('A note'))
  })

  // R1.3 — the palette was reachable only by typing '/', which nothing advertises.
  it('opens the quick-reply palette from the Quick button', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /quick/i }))
    expect(await screen.findByTestId('qr-q-1')).toBeInTheDocument()
  })

  it('keeps an existing draft when the Quick button opens the palette', async () => {
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'Half a sentence')
    await userEvent.click(screen.getByRole('button', { name: /quick/i }))
    expect(await screen.findByTestId('qr-q-1')).toBeInTheDocument()
    expect(box).toHaveValue('Half a sentence')
  })

  // Fix round 1: a forced-open palette has no term, so it never narrowed as you typed and
  // its document-level Enter handler stayed armed. Pressing Enter for a newline picked the
  // highlighted reply and replaced the whole draft with a template.
  it('releases the forced palette as soon as you type, so Enter still makes a newline', async () => {
    routes({ render: { body: 'A TEMPLATE THAT MUST NOT APPEAR', characters: 31, segments: 1 } })
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.click(screen.getByRole('button', { name: /quick/i }))
    await screen.findByTestId('qr-q-1')
    await userEvent.type(box, "Hi Sarah, I'll send someone up")
    expect(screen.queryByTestId('qr-q-1')).not.toBeInTheDocument()
    await userEvent.keyboard('{Enter}')
    expect(box).toHaveValue("Hi Sarah, I'll send someone up\n")
    expect(
      vi.mocked(fetch).mock.calls.some(([u, i]) => String(u).includes('/render') && i?.method === 'POST'),
    ).toBe(false)
  })

  it('does not leave the forced palette open over the box after a send', async () => {
    routes({ render: { body: 'A TEMPLATE THAT MUST NOT APPEAR', characters: 31, segments: 1 } })
    mount()
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'On our way')
    await userEvent.click(screen.getByRole('button', { name: /quick/i }))
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    await waitFor(() => expect(box).toHaveValue(''))
    expect(screen.queryByTestId('qr-q-1')).not.toBeInTheDocument()
    // Ctrl+Enter means send, never "pick the highlighted reply": the palette's document
    // listener must not also fire and repopulate the just-emptied box with a template.
    expect(
      vi.mocked(fetch).mock.calls.some(([u, i]) => String(u).includes('/render') && i?.method === 'POST'),
    ).toBe(false)
  })

  // Fix round 1: the note branch of submit() left assetId and draftPromptId armed, so the
  // next outbound message carried an attachment whose link was never in its body.
  it('disarms a picked asset when the draft is posted as a note instead', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /attach/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /WiFi card/ }))
    const box = screen.getByRole('textbox')
    await waitFor(() => expect((box as HTMLTextAreaElement).value).toContain('/a/wifi1'))
    await userEvent.click(screen.getByRole('button', { name: 'Note' }))
    await userEvent.click(screen.getByRole('button', { name: /add note/i }))
    await waitFor(() => expect(notePosts()).toHaveLength(1))

    await userEvent.click(screen.getByRole('button', { name: 'Reply' }))
    await userEvent.type(screen.getByRole('textbox'), 'Someone is on the way')
    await userEvent.keyboard('{Control>}{Enter}{/Control}')
    const sent = vi
      .mocked(fetch)
      .mock.calls.find(([u, i]) => String(u).includes('/messages') && i?.method === 'POST')
    expect(JSON.parse(String(sent![1]!.body))).toMatchObject({
      body: 'Someone is on the way',
      digitalAssetId: null,
    })
  })

  // Textarea's only focus affordance is focus:border-accent (it sets focus:outline-none),
  // and a plain one loses to the important !border-noteBorder that tints Note mode.
  it('keeps a focus indicator in Note mode', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Note' }))
    expect(screen.getByRole('textbox').className).toContain('focus:!border-accent')
  })

  it('opens the work-order modal from the composer', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /work order/i }))
    expect(await screen.findByRole('dialog')).toHaveTextContent(/create work order/i)
  })

  it('orders the composer actions Quick · Asset · Work order', async () => {
    mount()
    await screen.findByRole('textbox')
    const labels = screen
      .getAllByRole('button')
      .map((b) => b.textContent?.trim())
      .filter((t) => t === 'Quick' || t === 'Attach' || t === 'Work order')
    expect(labels).toEqual(['Quick', 'Attach', 'Work order'])
  })
})
