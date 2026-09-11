import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RenderedQuickReply } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aQuickReply } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { QuickRepliesAdmin } from './QuickRepliesAdmin'

const REPLIES = [
  aQuickReply({ id: 'q1', shortcut: '/wifi', title: 'WiFi details', usageCount: 212 }),
  aQuickReply({ id: 'q2', shortcut: '/shuttle', title: 'Airport shuttle', active: false, usageCount: 0 }),
]

// What GET /quick-replies/variables answers — server/app/domain/quick_replies.py VARIABLES.
const VARIABLES = [
  'guest_first_name', 'room_number', 'property_name', 'agent_first_name', 'departure_date',
]
// server/app/domain/quick_replies.py FALLBACKS, which is what a preview with no conversation uses.
const FALLBACKS: Record<string, string> = {
  guest_first_name: 'there', room_number: 'your room', property_name: 'the hotel',
  agent_first_name: 'the front desk', departure_date: 'soon',
}

/** Bodies POSTed to /quick-replies/preview, in order — the debounce assertion counts these. */
const previewed: string[] = []
/** Lets a test pin the numbers the server returns, so a client-side count cannot produce them. */
let previewOverride: Partial<RenderedQuickReply> | null = null

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
}

type Handler = (url: string, init?: RequestInit) => Promise<Response> | null

/**
 * `extra` beats every built-in route. A test that needs one call to fail must go through here
 * rather than `mockResolvedValueOnce`: the debounced preview fires on its own schedule, so a
 * one-shot mock can land on the preview instead of the write it was meant for.
 */
function serve(extra?: Handler) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const override = extra?.(url, init)
    if (override) return override
    if (url.includes('/quick-replies/preview')) {
      const sent = JSON.parse(String(init!.body)) as { body: string }
      previewed.push(sent.body)
      const rendered = sent.body.replace(/\{\{([a-z_]+)\}\}/g, (m, k: string) => FALLBACKS[k] ?? m)
      return json({ body: rendered, characters: rendered.length, segments: 1, ...previewOverride })
    }
    if (init && init.method && init.method !== 'GET') return json(aQuickReply())
    if (url.includes('/quick-replies/variables')) return json(VARIABLES)
    if (url.includes('/departments')) return json([aDepartment()])
    return json(REPLIES)
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <QuickRepliesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/quick-replies' },
  )
}

/** The panel's field errors and the counter both key off the last request, so read it back. */
function lastBody(method: string): Record<string, unknown> {
  const call = vi.mocked(fetch).mock.calls.filter(([, i]) => i?.method === method).at(-1)
  return JSON.parse(String(call![1]!.body)) as Record<string, unknown>
}

describe('QuickRepliesAdmin', () => {
  beforeEach(() => {
    previewed.length = 0
    previewOverride = null
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists replies with shortcut, title and usage', async () => {
    mount()
    expect(await screen.findByText('/wifi')).toBeInTheDocument()
    expect(screen.getByText('WiFi details')).toBeInTheDocument()
    expect(screen.getByText('212')).toBeInTheDocument()
  })

  it('reports the active and inactive counts', async () => {
    mount()
    expect(await screen.findByText(/1 active · 1 inactive/)).toBeInTheDocument()
  })

  it('shows no edit panel until something is selected', async () => {
    mount()
    await screen.findByText('/wifi')
    expect(screen.queryByLabelText('Body')).not.toBeInTheDocument()
  })

  it('opens the edit panel pre-filled when a row is clicked', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await waitFor(() => expect(screen.getByLabelText('Shortcut')).toHaveValue('/wifi'))
    expect(screen.getByLabelText('Title')).toHaveValue('WiFi details')
    expect(screen.getByLabelText('Body')).toHaveValue(REPLIES[0]!.body)
  })

  it('shows usage as read-only text, never as a field', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await waitFor(() => expect(screen.getByText(/212 uses/)).toBeInTheDocument())
    expect(screen.queryByLabelText(/uses/i)).not.toBeInTheDocument()
  })

  it('patches only on save, not on every keystroke', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    const title = await screen.findByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'WiFi info')
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'PATCH')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(String(patch![0])).toContain('/quick-replies/q1')
    expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ title: 'WiFi info' })
  })

  it('creates a new reply through POST', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /new quick reply/i }))
    await userEvent.type(screen.getByLabelText('Shortcut'), '/pool')
    await userEvent.type(screen.getByLabelText('Title'), 'Pool hours')
    await userEvent.type(screen.getByLabelText('Body'), 'The pool is open 7 AM-10 PM.')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({
      shortcut: '/pool',
      title: 'Pool hours',
    })
  })

  it('asks before deleting and only then calls DELETE', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'DELETE')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    const del = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'DELETE')
    expect(String(del![0])).toContain('/quick-replies/q1')
  })

  it('backs out of a delete on Keep', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }))
    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument()
  })

  it('shows the server error in the panel and keeps it open', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await screen.findByLabelText('Title')
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Shortcut already exists' } }, 400)
        : null,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Shortcut already exists')
    expect(screen.getByLabelText('Title')).toBeInTheDocument()
  })

  it('filters by shortcut or text', async () => {
    mount()
    await screen.findByText('/wifi')
    await userEvent.type(screen.getByPlaceholderText(/search/i), 'shuttle')
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('q=shuttle'))).toBe(true),
    )
  })

  // Regression test for the invalidation-key trap: qk.quickReplies(propertyId) with no search
  // term produces a key that does not match a search-filtered key. If a mutation invalidated
  // that exact key instead of the `quickRepliesAll` prefix, an edit made while a search filter
  // is active would save but the filtered list would never refetch — with no error anywhere.
  it('refreshes a search-filtered list after an edit made under that filter', async () => {
    mount()
    await screen.findByText('/wifi')
    await userEvent.type(screen.getByPlaceholderText(/search/i), 'shuttle')
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('q=shuttle'))).toBe(true),
    )
    const filteredGets = () =>
      vi
        .mocked(fetch)
        .mock.calls.filter(
          ([u, i]) => (!i || !i.method || i.method === 'GET') && String(u).includes('q=shuttle'),
        ).length
    const before = filteredGets()

    await userEvent.click(await screen.findByText('WiFi details'))
    const title = await screen.findByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'WiFi info')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    // A save that only invalidated the exact (unfiltered) key would never re-fetch the
    // still-active filtered query, so `filteredGets()` would stay flat at `before`.
    await waitFor(() => expect(filteredGets()).toBeGreaterThan(before))
  })

  // --- A2: the chips, the counter, the preview, and the two missing inputs ---

  it('renders one Insert chip per variable the server supports', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await screen.findByLabelText('Body')
    // Five, not the mockup's four: the mockup omits property_name (ruling D68), and the list is
    // fetched rather than hardcoded, so a server-side change reaches the UI on its own.
    for (const name of VARIABLES) {
      expect(await screen.findByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('inserts a variable at the caret, not at the end, and leaves the caret after it', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new quick reply/i }))
    const body = (await screen.findByLabelText('Body')) as HTMLTextAreaElement
    await user.type(body, 'Hi , welcome')
    await screen.findByRole('button', { name: 'guest_first_name' })
    body.setSelectionRange(3, 3) // between "Hi " and ","
    await user.click(screen.getByRole('button', { name: 'guest_first_name' }))

    expect(body).toHaveValue('Hi {{guest_first_name}}, welcome')
    expect(body).toHaveFocus()
    expect(body.selectionStart).toBe(3 + '{{guest_first_name}}'.length)
    expect(body.selectionEnd).toBe(body.selectionStart)
  })

  it('replaces the selection when the chip is clicked with text selected', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new quick reply/i }))
    const body = (await screen.findByLabelText('Body')) as HTMLTextAreaElement
    await user.type(body, 'Hi NAME, welcome')
    await screen.findByRole('button', { name: 'guest_first_name' })
    body.setSelectionRange(3, 7) // "NAME"
    await user.click(screen.getByRole('button', { name: 'room_number' }))

    expect(body).toHaveValue('Hi {{room_number}}, welcome')
  })

  it('renders the counter from the server response, never from a local count', async () => {
    // Numbers no client-side counter could produce for an 11-character, one-segment body. If the
    // counter is ever recomputed in TypeScript this test fails.
    previewOverride = { characters: 4242, segments: 3 }
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new quick reply/i }))
    await user.type(await screen.findByLabelText('Body'), 'Short body.')
    expect(await screen.findByText('4242 chars · 3 segments')).toBeInTheDocument()
  })

  it('pluralises a single segment', async () => {
    previewOverride = { characters: 138, segments: 1 }
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new quick reply/i }))
    await user.type(await screen.findByLabelText('Body'), 'Short body.')
    expect(await screen.findByText('138 chars · 1 segment')).toBeInTheDocument()
  })

  it('previews the draft body against the sample values, with no conversation', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new quick reply/i }))
    const body = await screen.findByLabelText('Body')
    // Built with the chips rather than typed: userEvent treats `{{` as an escape sequence, and
    // this exercises the chip and the preview together anyway.
    await user.type(body, 'Hi ')
    await user.click(await screen.findByRole('button', { name: 'guest_first_name' }))
    await user.type(body, ' in ')
    await user.click(screen.getByRole('button', { name: 'room_number' }))
    expect(body).toHaveValue('Hi {{guest_first_name}} in {{room_number}}')
    expect(await screen.findByText('Hi there in your room')).toBeInTheDocument()
    expect(screen.getByText(/Preview · sample values/)).toBeInTheDocument()
    // No conversation is chosen, fetched or sent - Property B has none, and a stored-row render
    // could not show an unsaved draft anyway.
    expect(lastBody('POST')).toEqual({ body: 'Hi {{guest_first_name}} in {{room_number}}' })
    expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/conversations'))).toBe(false)
  })

  it('debounces the preview instead of firing one request per keystroke', async () => {
    // Real keystroke spacing, deliberately: with `delay: null` the whole burst lands inside one
    // task and even a 0 ms debounce coalesces it, which would make this test unable to fail.
    const user = userEvent.setup({ delay: 20 })
    mount()
    await user.click(await screen.findByRole('button', { name: /new quick reply/i }))
    const body = await screen.findByLabelText('Body')
    expect(previewed).toEqual([]) // empty body: the server 400s on one, so it is never asked

    const text = 'The pool is open 7 AM to 10 PM.' // 31 keystrokes, ~20 ms apart
    await user.type(body, text)
    await waitFor(() => expect(previewed.at(-1)).toBe(text))
    // Undebounced this is one round trip per character; 300 ms of quiet makes it one in total.
    expect(previewed.length).toBeLessThan(5)
    await waitFor(() => expect(screen.getByText(/chars/)).toBeInTheDocument())
  })

  it('sends locale on patch and it survives the round trip', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi details'))
    const locale = await screen.findByLabelText('Locale')
    expect(locale).toHaveValue('en')
    await user.clear(locale)
    await user.type(locale, 'fr-CA')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    // A1 added `locale` to QuickReplyPatch; the old code stripped it from the payload.
    await waitFor(() => expect(lastBody('PATCH')).toMatchObject({ locale: 'fr-CA' }))
  })

  it('caps locale at the eight characters the column holds', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi details'))
    const locale = await screen.findByLabelText('Locale')
    await user.clear(locale)
    await user.type(locale, 'abcdefghij')
    expect(locale).toHaveValue('abcdefgh')
  })

  it('sends category on patch', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi details'))
    await user.type(await screen.findByLabelText('Category'), 'connectivity')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(lastBody('PATCH')).toMatchObject({ category: 'connectivity' }))
  })

  it('clears category back to null when the input is emptied', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi details'))
    const category = await screen.findByLabelText('Category')
    await user.type(category, 'connectivity')
    await user.clear(category)
    await user.click(screen.getByRole('button', { name: 'Save' }))
    // `category` is nullable on the server, so clearing it is a real edit, not a 400.
    await waitFor(() => expect(lastBody('PATCH')).toMatchObject({ category: null }))
  })

  it('shows a 400 that names a field against that field, not only in the banner', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi details'))
    await screen.findByLabelText('Locale')
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Cannot be cleared: locale',
                          details: { locale: 'required' } } }, 400)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const message = await screen.findByText('required')
    // It must sit with the Locale input, not float somewhere in the panel.
    expect(message.parentElement).toContainElement(screen.getByLabelText('Locale'))
  })

  it('surfaces a Pydantic field rejection against its input too', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi details'))
    await screen.findByLabelText('Shortcut')
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Invalid request body',
                          details: [{ type: 'string_pattern_mismatch', loc: ['shortcut'],
                                      msg: 'String should match pattern' }] } }, 400)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const message = await screen.findByText('String should match pattern')
    expect(message.parentElement).toContainElement(screen.getByLabelText('Shortcut'))
  })

  it('shows the preview error instead of passing a stale render off as current', async () => {
    serve((url) =>
      url.includes('/quick-replies/preview')
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Body is too long' } }, 400)
        : null,
    )
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new quick reply/i }))
    await user.type(await screen.findByLabelText('Body'), 'Anything at all.')
    expect(await screen.findByText(/Preview unavailable: Body is too long/)).toBeInTheDocument()
    expect(screen.queryByText(/chars/)).not.toBeInTheDocument()
  })
})
