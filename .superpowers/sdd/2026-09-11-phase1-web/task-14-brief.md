### Task 14: Composer — quick replies, assets, segment counter, optimistic send, retry

**Files:**
- Create: `web/src/features/inbox/Composer.tsx`, `QuickReplyPalette.tsx`, `AssetPicker.tsx`
- Create: `web/src/api/hooks/content.ts`
- Modify: `web/src/api/hooks/conversations.ts` (add `useSendMessage`, `useRetryMessage`), `ConversationView.tsx` (mount the composer)
- Test: `web/src/features/inbox/QuickReplyPalette.test.tsx`, `web/src/features/inbox/Composer.test.tsx`

**Interfaces:**
- Consumes: `segmentCount` / `charCount` (Task 10), `useConversation` (Task 12), `useRealtime` (Task 11), primitives (Task 4).
- Produces:
  - `content.ts`: `useQuickReplies(q?: string)`, `useRenderQuickReply()` (`POST quick-replies/<id>/render {conversationId}` → `RenderedQuickReply`), `useAssets()`, `useCategories()`
  - `useSendMessage(conversationId)` → `POST conversations/<id>/messages`, **optimistic**
  - `useRetryMessage(conversationId)` → `POST conversations/<id>/messages/<mid>/retry`
  - `filterQuickReplies(replies: QuickReplyOut[], term: string): QuickReplyOut[]` — exported from `QuickReplyPalette.tsx` for its own test
  - `Composer({ conversationId, conversation, draftBody?, draftPromptId?, onDraftConsumed? })` — `draftBody`/`draftPromptId` are how Task 15's prompt banner loads a draft; the composer passes `draftPromptId` through on send so the server can mark the prompt sent

**Two of §7's four required web tests live here:** the segment counter and the quick-reply palette filtering.

**Interpolation is the server's job.** `POST quick-replies/<id>/render {conversationId}` returns the interpolated `body` plus its `characters` and `segments`. The client never substitutes `{{guest_first_name}}` itself — the server owns the token vocabulary, and a client that guessed would send a literal `{{…}}` to a guest the day a token is renamed.

**Palette behaviour (§5.3):** `/` **at the start of an empty composer** opens the palette. Typing filters by shortcut and body. `↑`/`↓` move the selection, `Enter` inserts the rendered text and closes, `Escape` closes and leaves the typed text alone. Filtering is case-insensitive and matches a shortcut prefix *or* a substring of the title or body; shortcut-prefix matches sort first, because someone typing `/wi` means `/wifi`.

**Asset picker** appends ` <origin>/a/<shortCode>` to the draft and sets `digitalAssetId` on the send. The short link is what the guest receives; `/a/<code>` 302s to the real URL.

**Segment counter** reads `N chars · M segments`, in mono `text-text3`, turning `text-warnText` at 2 segments and `text-dangerText` past 4 — a four-segment SMS is a cost signal an agent should see before sending, not on the invoice.

**Optimistic send (§5.3).** On submit, a synthetic message with `id: 'optimistic-<n>'`, `deliveryStatus: 'queued'`, `direction: 'outbound'`, `authorType: 'staff'` and the current user's id is pushed into the cached `ConversationDetail`, and the textarea clears immediately. Reconciliation:
- **Success** — the response is the real `MessageOut`; replace the optimistic entry by id. The subsequent `message.created` / `message.status_changed` events (Task 11) invalidate the detail, so the real row wins regardless.
- **Failure** — remove the optimistic entry, restore the text into the textarea, and show the error. A `422 CONSENT_OPTED_OUT` must show the server's message: the server creates *no* message row for a rejected send (§6), so leaving a ghost bubble would be a lie.

**Ctrl/Cmd+Enter sends.** Plain Enter inserts a newline — an agent mid-sentence must not fire a message at a guest.

**Composing presence.** On textarea focus, `setPresence(conversationId, 'composing')`; on blur, back to `'viewing'`. This is what drives "Marcus is replying" for everyone else (ruling R2).

**The composer stays enabled for an opted-out guest** (§5.3) with a warning above it: the server enforces consent, and disabling the box would hide *why* from the agent.

- [ ] **Step 1: Write `web/src/api/hooks/content.ts`**

```ts
import { useMutation, useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { AssetOut, CategoryOut, QuickReplyOut, RenderedQuickReply } from '../types'

export function useQuickReplies(q?: string) {
  const { propertyId } = useSession()
  return useQuery<QuickReplyOut[], ApiError>({
    queryKey: qk.quickReplies(propertyId, q),
    queryFn: () =>
      api<QuickReplyOut[]>(
        propertyPath(propertyId, `quick-replies${q ? `?q=${encodeURIComponent(q)}` : ''}`),
      ),
    staleTime: 60_000,
  })
}

export function useRenderQuickReply() {
  const { propertyId } = useSession()
  return useMutation<RenderedQuickReply, ApiError, { id: string; conversationId: string }>({
    mutationFn: ({ id, conversationId }) =>
      api<RenderedQuickReply>(propertyPath(propertyId, `quick-replies/${id}/render`), {
        method: 'POST',
        json: { conversationId },
      }),
  })
}

export function useAssets() {
  const { propertyId } = useSession()
  return useQuery<AssetOut[], ApiError>({
    queryKey: qk.assets(propertyId),
    queryFn: () => api<AssetOut[]>(propertyPath(propertyId, 'assets')),
    staleTime: 60_000,
  })
}

export function useCategories() {
  const { propertyId } = useSession()
  return useQuery<CategoryOut[], ApiError>({
    queryKey: qk.categories(propertyId),
    queryFn: () => api<CategoryOut[]>(propertyPath(propertyId, 'resolution-categories')),
    staleTime: 5 * 60_000,
  })
}
```

- [ ] **Step 2: Add the send and retry mutations to `conversations.ts`**

```ts
import type { MessageOut, SendMessageRequest } from '../types'

let optimisticCounter = 0

export function useSendMessage(conversationId: string) {
  const { propertyId, user } = useSession()
  const client = useQueryClient()
  const key = qk.conversation(propertyId, conversationId)

  return useMutation<MessageOut, ApiError, SendMessageRequest, { optimisticId: string }>({
    mutationFn: (body) =>
      api<MessageOut>(propertyPath(propertyId, `conversations/${conversationId}/messages`), {
        method: 'POST',
        json: body,
      }),
    onMutate: async (body) => {
      await client.cancelQueries({ queryKey: key })
      const optimisticId = `optimistic-${++optimisticCounter}`
      client.setQueryData<ConversationDetail>(key, (current) =>
        current
          ? {
              ...current,
              messages: [
                ...current.messages,
                {
                  id: optimisticId,
                  conversationId,
                  direction: 'outbound',
                  channel: current.channelPrimary,
                  authorType: 'staff',
                  authorUserId: user.id,
                  body: body.body,
                  deliveryStatus: 'queued',
                  sentAt: null,
                  deliveredAt: null,
                  providerErrorCode: null,
                  providerErrorMessage: null,
                  digitalAssetId: body.digitalAssetId ?? null,
                  redacted: false,
                },
              ],
            }
          : current,
      )
      return { optimisticId }
    },
    onSuccess: (real, _body, context) => {
      client.setQueryData<ConversationDetail>(key, (current) =>
        current
          ? {
              ...current,
              messages: current.messages.map((m) => (m.id === context?.optimisticId ? real : m)),
            }
          : current,
      )
    },
    onError: (_error, _body, context) => {
      // A rejected send creates no server row (§6) — drop the bubble rather than leave a ghost.
      client.setQueryData<ConversationDetail>(key, (current) =>
        current
          ? { ...current, messages: current.messages.filter((m) => m.id !== context?.optimisticId) }
          : current,
      )
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: qk.conversationsAll(propertyId) })
    },
  })
}

export function useRetryMessage(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<MessageOut, ApiError, { messageId: string }>({
    mutationFn: ({ messageId }) =>
      api<MessageOut>(
        propertyPath(propertyId, `conversations/${conversationId}/messages/${messageId}/retry`),
        { method: 'POST' },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
    },
  })
}
```

- [ ] **Step 3: Write the failing palette test (§7 requirement)**

`web/src/features/inbox/QuickReplyPalette.test.tsx`:

```tsx
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
})
```

- [ ] **Step 4: Write the failing composer test (§7 requirement: the segment counter)**

`web/src/features/inbox/Composer.test.tsx`:

```tsx
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
    expect(box).not.toHaveValue(expect.stringContaining('{{'))
  })

  it('appends a short link when an asset is picked', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /attach/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /WiFi card/ }))
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(expect.stringContaining('/a/wifi1')))
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
})
```

- [ ] **Step 5: Run them to verify they fail**

```bash
cd web && npx vitest run src/features/inbox/QuickReplyPalette.test.tsx src/features/inbox/Composer.test.tsx
```

Expected: FAIL — neither module resolves.

- [ ] **Step 6: Write `QuickReplyPalette.tsx`**

```tsx
import { useEffect, useState } from 'react'
import type { QuickReplyOut } from '../../api/types'
import { cn } from '../../lib/cn'

/** §5.3: filter by shortcut and body. Shortcut-prefix matches rank first. */
export function filterQuickReplies(replies: QuickReplyOut[], term: string): QuickReplyOut[] {
  const active = replies.filter((r) => r.active)
  const needle = term.trim().toLowerCase().replace(/^\//, '')
  if (!needle) return active

  const byShortcut: QuickReplyOut[] = []
  const byText: QuickReplyOut[] = []
  for (const reply of active) {
    if (reply.shortcut.toLowerCase().replace(/^\//, '').startsWith(needle)) byShortcut.push(reply)
    else if (
      reply.title.toLowerCase().includes(needle) ||
      reply.body.toLowerCase().includes(needle)
    )
      byText.push(reply)
  }
  return [...byShortcut, ...byText]
}

export function QuickReplyPalette({
  replies,
  term,
  onPick,
  onClose,
}: {
  replies: QuickReplyOut[]
  term: string
  onPick: (reply: QuickReplyOut) => void
  onClose: () => void
}) {
  const matches = filterQuickReplies(replies, term)
  const [index, setIndex] = useState(0)

  // A new term means a new list; keep the cursor in range rather than off the end.
  useEffect(() => {
    setIndex(0)
  }, [term])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setIndex((i) => Math.min(i + 1, matches.length - 1))
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        setIndex((i) => Math.max(i - 1, 0))
      } else if (event.key === 'Enter') {
        const picked = matches[index]
        if (picked) {
          event.preventDefault()
          onPick(picked)
        }
      } else if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [matches, index, onPick, onClose])

  if (matches.length === 0) return null

  return (
    <ul
      role="listbox"
      className="absolute bottom-full left-0 right-0 mb-2 max-h-64 overflow-y-auto rounded-card border border-border2 bg-surface py-1"
    >
      {matches.map((reply, i) => (
        <li
          key={reply.id}
          data-testid={`qr-${reply.id}`}
          role="option"
          aria-selected={i === index}
          onMouseDown={(event) => {
            event.preventDefault() // keep focus in the textarea
            onPick(reply)
          }}
          className={cn(
            'cursor-pointer px-3 py-2',
            i === index ? 'bg-surface2' : 'hover:bg-surface2',
          )}
        >
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs font-semibold text-roomNum">{reply.shortcut}</span>
            <span className="text-[13px] font-semibold">{reply.title}</span>
          </div>
          <p className="truncate text-xs text-text3">{reply.body}</p>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 7: Write `AssetPicker.tsx`**

```tsx
import { useAssets } from '../../api/hooks/content'
import type { AssetOut } from '../../api/types'
import { Dropdown } from '../../components/ui'

export function AssetPicker({ onPick }: { onPick: (asset: AssetOut) => void }) {
  const { data: assets } = useAssets()
  const available = (assets ?? []).filter((a) => a.active)

  return (
    <Dropdown label="Attach">
      {(close) =>
        available.length === 0 ? (
          <p className="px-3 py-2 text-xs text-text3">No assets</p>
        ) : (
          <>
            {available.map((asset) => (
              <button
                key={asset.id}
                role="menuitem"
                className="flex w-full flex-col items-start px-3 py-2 text-left hover:bg-surface2"
                onClick={() => {
                  close()
                  onPick(asset)
                }}
              >
                <span className="text-[13px] font-semibold">{asset.name}</span>
                <span className="font-mono text-xs text-text3">/a/{asset.shortCode}</span>
              </button>
            ))}
          </>
        )
      }
    </Dropdown>
  )
}
```

- [ ] **Step 8: Write `Composer.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react'
import { useQuickReplies, useRenderQuickReply } from '../../api/hooks/content'
import { useSendMessage } from '../../api/hooks/conversations'
import { useRealtime } from '../../api/ws'
import type { ConversationDetail } from '../../api/types'
import { Button, Textarea } from '../../components/ui'
import { cn } from '../../lib/cn'
import { charCount, segmentCount } from '../../lib/segments'
import { AssetPicker } from './AssetPicker'
import { QuickReplyPalette } from './QuickReplyPalette'

export function Composer({
  conversationId,
  conversation,
  draftBody,
  draftPromptId: draftPromptIdIn,
  onDraftConsumed,
}: {
  conversationId: string
  conversation: ConversationDetail
  draftBody?: string
  draftPromptId?: string | null
  onDraftConsumed?: () => void
}) {
  const [body, setBody] = useState('')
  const [assetId, setAssetId] = useState<string | null>(null)
  const [draftPromptId, setDraftPromptId] = useState<string | null>(null)
  const box = useRef<HTMLTextAreaElement>(null)
  const send = useSendMessage(conversationId)
  const { data: replies } = useQuickReplies()
  const render = useRenderQuickReply()
  const { setPresence } = useRealtime()

  // A draft handed down from the prompt banner (Task 15) loads once, then clears.
  // This must be an effect, not a render-phase setState — the latter loops.
  useEffect(() => {
    if (draftBody) {
      setBody(draftBody)
      setDraftPromptId(draftPromptIdIn ?? null)
      box.current?.focus()
      onDraftConsumed?.()
    }
  }, [draftBody, draftPromptIdIn, onDraftConsumed])

  // The palette opens only when '/' starts the draft — 'either/or' must not trigger it.
  const paletteOpen = body.startsWith('/') && !body.includes(' ') && !body.includes('\n')
  const segments = segmentCount(body)
  const characters = charCount(body)
  const optedOut = conversation.guest.smsConsentStatus === 'opted_out'

  function submit() {
    const trimmed = body.trim()
    if (!trimmed || send.isPending) return
    send.mutate(
      {
        body: trimmed,
        digitalAssetId: assetId,
        draftPromptId,
      },
      {
        onError: () => setBody(trimmed), // give the text back; retyping is the real cost
      },
    )
    setBody('')
    setAssetId(null)
    setDraftPromptId(null)
  }

  return (
    <div className="border-t border-border p-3">
      {optedOut ? (
        <p className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          This guest has opted out of SMS. A send will be rejected unless they text START.
        </p>
      ) : null}

      {send.error ? (
        <p role="alert" className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {send.error.message}
        </p>
      ) : null}

      <div className="relative">
        {paletteOpen && replies ? (
          <QuickReplyPalette
            replies={replies}
            term={body}
            onClose={() => setBody('')}
            onPick={(reply) => {
              // The server interpolates; we never substitute tokens client-side.
              render.mutate(
                { id: reply.id, conversationId },
                {
                  onSuccess: (rendered) => {
                    setBody(rendered.body)
                    box.current?.focus()
                  },
                },
              )
            }}
          />
        ) : null}

        <Textarea
          ref={box}
          rows={3}
          value={body}
          placeholder="Type a reply, or / for a quick reply"
          onChange={(event) => setBody(event.target.value)}
          onFocus={() => setPresence(conversationId, 'composing')}
          onBlur={() => setPresence(conversationId, 'viewing')}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
              event.preventDefault()
              submit()
            }
          }}
        />
      </div>

      <div className="mt-2 flex items-center gap-3">
        <AssetPicker
          onPick={(asset) => {
            setAssetId(asset.id)
            setBody((current) => `${current}${current ? ' ' : ''}${window.location.origin}/a/${asset.shortCode}`)
          }}
        />
        {segments > 0 ? (
          <span
            data-testid="segment-counter"
            className={cn(
              'font-mono text-xs',
              segments > 4 ? 'text-dangerText' : segments > 1 ? 'text-warnText' : 'text-text3',
            )}
          >
            {characters} chars · {segments} segment{segments === 1 ? '' : 's'}
          </span>
        ) : null}
        <Button
          variant="primary"
          className="ml-auto"
          loading={send.isPending}
          onClick={submit}
          title="Ctrl+Enter"
        >
          Send
        </Button>
      </div>
    </div>
  )
}
```

`Textarea` must forward its ref for `box` to work — wrap it in `forwardRef` in `components/ui/Textarea.tsx`:

```tsx
import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return (
      <textarea
        {...rest}
        ref={ref}
        className={cn(
          'w-full rounded border border-border3 bg-surface2 p-3 text-sm leading-relaxed text-text',
          'placeholder:text-text4 focus:border-accent focus:outline-none',
          className,
        )}
      />
    )
  },
)
```

- [ ] **Step 9: Mount the composer and the retry handler in `ConversationView.tsx`**

Add below the timeline `div`, and pass `onRetry` into each failed outbound bubble:

```tsx
const retry = useRetryMessage(conversationId)
// …inside the message branch of the timeline map:
//   onRetry={
//     entry.message.deliveryStatus === 'failed' || entry.message.deliveryStatus === 'undelivered'
//       ? () => retry.mutate({ messageId: entry.message.id })
//       : undefined
//   }
// …and after the timeline div:
<Composer conversationId={conversationId} conversation={data} />
```

- [ ] **Step 10: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 10 filter tests, 6 palette tests, 16 composer tests.

- [ ] **Step 11: Verify against the real server**

As Ava on the 412 conversation: type `/` and the palette opens with the ~15 seeded replies; type `wi`, press Enter, and the box fills with the **interpolated** body naming Sarah (no `{{ }}`). Attach the WiFi card and confirm the appended `/a/<code>`. Watch the counter cross into amber past 160 characters. Send: the bubble appears instantly as **Sending…**, then **Sent**, then **Delivered** without a refresh (the worker plus the socket). Open the conversation whose guest ends `0000`, send, and after the worker ticks it turns **Failed · 30007** with a working **Retry**. Open the opted-out guest's conversation, send, and confirm the red `422` message and that your text comes back.

- [ ] **Step 12: Commit**

```bash
git add web/src/features/inbox web/src/api/hooks/content.ts web/src/api/hooks/conversations.ts \
        web/src/components/ui/Textarea.tsx
git commit -m "feat(web): composer with quick replies, assets, segment counter and optimistic send"
```

---

