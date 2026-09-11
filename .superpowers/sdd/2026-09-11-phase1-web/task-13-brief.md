### Task 13: Conversation thread, notes, guest panel

**Files:**
- Create: `web/src/features/inbox/ConversationView.tsx` (replacing Task 12's stub), `MessageBubble.tsx`, `GuestPanel.tsx`, `ConversationHeader.tsx`
- Modify: `web/src/api/hooks/conversations.ts` (add `useAddNote`, `usePatchConversation`)
- Test: `web/src/features/inbox/MessageBubble.test.tsx`, `web/src/features/inbox/ConversationView.test.tsx`, `web/src/features/inbox/presenceLine.test.ts`, `web/src/features/inbox/GuestPanel.test.tsx`

**Interfaces:**
- Consumes: `useConversation` / `useStaff` / `useDepartments` (Task 12), `useRealtime` (Task 11), `SlaChip` (Task 10), factories (Task 12).
- Produces:
  - `useAddNote(conversationId)` → `POST conversations/<id>/notes {body}`, invalidates that detail
  - `usePatchConversation(conversationId)` → `PATCH conversations/<id>` with `ConversationPatch`, invalidates the detail and every list
  - `MessageBubble({ message, authorName })`, `ConversationHeader({ conversation })`, `GuestPanel({ conversation })`, `ConversationView({ conversationId })`

**Thread rendering, from the mockups' `.bubble` / `.in` / `.out` / `.meta` and §5.3:**

| Kind | Treatment |
|---|---|
| Inbound guest message | left, `bg-surface2` + `border-border2`, `text-text` |
| Outbound staff message | right, `bg-outBg` `text-outText` |
| `authorType` `system` or `automation` | left, `bg-autoBg` `text-autoText` `border-autoBorder`, labelled `Automatic` |
| Internal note | full width, `bg-noteBg` `border-noteBorder` `text-noteText`, labelled **Internal** with a `text-noteIcon` marker |
| `redacted: true` | a `Badge tone="warn"` reading **Card number redacted** under the bubble (§6) |

Max bubble width 470 px, radius 10 px, 12/14 px padding, 14.5 px text. The meta line under each bubble is 12 px `text-text3`: the clock time, the author's first name for staff messages, and the delivery status for outbound ones.

**Delivery status copy** (`DeliveryStatus`): `queued` → `Sending…`; `sent` → `Sent`; `delivered` → `Delivered`; `failed`/`undelivered` → `Failed` in `text-dangerText`, followed by `providerErrorCode` and a **Retry** button (Task 14 owns the retry call; this task renders the state).

**Notes are interleaved by time, not appended.** `ConversationDetail` returns `messages` and `notes` as separate arrays (deliberately — `GuestThread` must never be able to carry a note). The view merges them into one timeline sorted by `sentAt`/`createdAt` so the thread reads chronologically. A note's timestamp is `createdAt`; a message with a null `sentAt` (queued) sorts last.

**Header** shows the room number in mono `roomNum`, the guest's name, channel/tier/stay-count chips (`SMS · GOLD · 4TH STAY` in the mockup), the SLA chip, and presence text from §5.3: `Marcus is viewing` / `Marcus is replying`, in a `Badge tone="presence"`. With more than one watcher it reads `Marcus and 2 others are viewing`. The current user is excluded from that line — telling Ava that Ava is viewing is noise.

**Guest panel** (right column, `w-[300px]`, `border-l border-border`, `bg-bg2`), sections with the mockups' `.panel-h` heading style, in this order: guest (name, phone in mono, loyalty tier, VIP), stay (room, type, arrival→departure, adults/children, stay count), **consent status** (a `Badge` — `Opted in` ok / `Opted out` danger / `Unknown` neutral), open work orders (title + status, linking to `/app/work-orders/<id>`), pending draft prompts (count), and recent notes. §5.2 requires exactly these.

- [ ] **Step 1: Add the two mutations to `web/src/api/hooks/conversations.ts`**

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { ConversationPatch, NoteOut } from '../types'

export function useAddNote(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<NoteOut, ApiError, { body: string }>({
    mutationFn: (body) =>
      api<NoteOut>(propertyPath(propertyId, `conversations/${conversationId}/notes`), {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
    },
  })
}

export function usePatchConversation(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<ConversationDetail, ApiError, ConversationPatch>({
    mutationFn: (patch) =>
      api<ConversationDetail>(propertyPath(propertyId, `conversations/${conversationId}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: () => {
      // Assignment, status and snooze all change which filters this belongs to.
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
      void client.invalidateQueries({ queryKey: qk.conversationsAll(propertyId) })
    },
  })
}
```

- [ ] **Step 2: Write the failing tests**

`web/src/features/inbox/MessageBubble.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { aMessage } from '../../test/factories'
import { MessageBubble } from './MessageBubble'

describe('MessageBubble', () => {
  it('renders an inbound guest message on the left with the surface treatment', () => {
    render(<MessageBubble message={aMessage()} authorName={null} />)
    const bubble = screen.getByTestId('bubble')
    expect(bubble.className).toContain('bg-surface2')
    expect(screen.getByTestId('bubble-row').className).toContain('justify-start')
  })

  it('renders an outbound staff message on the right with the outbound treatment', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', authorType: 'staff', authorUserId: 'u-ava' })}
        authorName="Ava"
      />,
    )
    expect(screen.getByTestId('bubble').className).toContain('bg-outBg')
    expect(screen.getByTestId('bubble-row').className).toContain('justify-end')
    expect(screen.getByText(/Ava/)).toBeInTheDocument()
  })

  it('labels an automated message', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', authorType: 'automation' })}
        authorName={null}
      />,
    )
    expect(screen.getByText('Automatic')).toBeInTheDocument()
    expect(screen.getByTestId('bubble').className).toContain('bg-autoBg')
  })

  it('shows a redaction chip when the card number was masked (§6)', () => {
    render(
      <MessageBubble
        message={aMessage({ redacted: true, body: 'my card is **** **** **** 1234' })}
        authorName={null}
      />,
    )
    expect(screen.getByText('Card number redacted')).toBeInTheDocument()
  })

  it('shows Sending… while queued', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', deliveryStatus: 'queued', sentAt: null })}
        authorName="Ava"
      />,
    )
    expect(screen.getByText('Sending…')).toBeInTheDocument()
  })

  it('shows Delivered once delivered', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', deliveryStatus: 'delivered' })}
        authorName="Ava"
      />,
    )
    expect(screen.getByText('Delivered')).toBeInTheDocument()
  })

  it('shows the provider error and a retry affordance on failure', () => {
    render(
      <MessageBubble
        message={aMessage({
          direction: 'outbound',
          deliveryStatus: 'failed',
          providerErrorCode: '30007',
          providerErrorMessage: 'Carrier rejected',
        })}
        authorName="Ava"
        onRetry={() => {}}
      />,
    )
    const failure = screen.getByText(/Failed/)
    expect(failure.className).toContain('dangerText')
    expect(screen.getByText(/30007/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('shows no delivery status on an inbound message — the guest sent it', () => {
    render(<MessageBubble message={aMessage()} authorName={null} />)
    expect(screen.queryByText('Delivered')).not.toBeInTheDocument()
  })
})
```

`web/src/features/inbox/ConversationView.test.tsx` — the tests that matter here are the timeline merge, the note treatment, and the presence line:

```tsx
import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RealtimeProvider } from '../../api/ws'
import { SessionProvider } from '../../auth/SessionContext'
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
      <RealtimeProvider>
        <ConversationView conversationId="c-1" />
      </RealtimeProvider>
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
    expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText(/GOLD/i)).toBeInTheDocument()
    expect(screen.getByText(/4TH STAY/i)).toBeInTheDocument()
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
    expect(await screen.findByText(/opted out/i)).toBeInTheDocument()
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
```

`web/src/features/inbox/presenceLine.test.ts` — the presence copy is pure logic, so it is tested directly rather than through a socket:

```ts
import { describe, expect, it } from 'vitest'
import { presenceLine } from './ConversationHeader'

describe('presenceLine', () => {
  it('names a single viewer', () => {
    expect(presenceLine(['Marcus'], false)).toBe('Marcus is viewing')
  })

  it('says replying when someone is composing', () => {
    expect(presenceLine(['Marcus'], true)).toBe('Marcus is replying')
  })

  it('collapses two people to one other', () => {
    expect(presenceLine(['Marcus', 'Jordan'], false)).toBe('Marcus and 1 other are viewing')
  })

  it('pluralises beyond two', () => {
    expect(presenceLine(['Marcus', 'Jordan', 'Ava'], false)).toBe('Marcus and 2 others are viewing')
  })

  it('returns an empty string for nobody, so the caller renders no chip', () => {
    expect(presenceLine([], false)).toBe('')
  })
})
```

`web/src/features/inbox/GuestPanel.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversationDetail, aGuest, aStay } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { GuestPanel } from './GuestPanel'
import { aWorkOrder, aDraftPrompt, aNote } from '../../test/factories'

function mount(detail = aConversationDetail()) {
  return renderWithProviders(
    <SessionProvider>
      <GuestPanel conversation={detail} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: '/app/inbox/c-1' },
  )
}

describe('GuestPanel', () => {
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
})
```

- [ ] **Step 3: Run them to verify they fail**

```bash
cd web && npx vitest run src/features/inbox
```

Expected: FAIL — `MessageBubble` and `GuestPanel` do not resolve; `ConversationView` is still Task 12's stub.

- [ ] **Step 4: Write `MessageBubble.tsx`**

```tsx
import type { MessageOut } from '../../api/types'
import { Badge, Button } from '../../components/ui'
import { cn } from '../../lib/cn'
import { formatClock } from '../../lib/time'

const STATUS_COPY: Record<MessageOut['deliveryStatus'], string> = {
  queued: 'Sending…',
  sent: 'Sent',
  delivered: 'Delivered',
  failed: 'Failed',
  undelivered: 'Failed',
}

export function MessageBubble({
  message,
  authorName,
  onRetry,
}: {
  message: MessageOut
  authorName: string | null
  onRetry?: () => void
}) {
  const outbound = message.direction === 'outbound'
  const automated = message.authorType === 'system' || message.authorType === 'automation'
  const failed = message.deliveryStatus === 'failed' || message.deliveryStatus === 'undelivered'

  return (
    <div
      data-testid="bubble-row"
      className={cn('flex w-full', outbound && !automated ? 'justify-end' : 'justify-start')}
    >
      <div className="max-w-[470px]">
        <div
          data-testid="bubble"
          className={cn(
            'rounded-card px-3.5 py-3 text-[14.5px] leading-relaxed',
            automated
              ? 'border border-autoBorder bg-autoBg text-autoText'
              : outbound
                ? 'bg-outBg text-outText'
                : 'border border-border2 bg-surface2 text-text',
          )}
        >
          {message.body}
        </div>

        {message.redacted ? (
          <Badge tone="warn" className="mt-1.5">
            Card number redacted
          </Badge>
        ) : null}

        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-text3">
          {automated ? <span>Automatic</span> : null}
          {message.sentAt ? <span>{formatClock(message.sentAt)}</span> : null}
          {authorName && !automated ? <span>{authorName}</span> : null}
          {outbound ? (
            <span className={failed ? 'font-semibold text-dangerText' : undefined}>
              {STATUS_COPY[message.deliveryStatus]}
              {failed && message.providerErrorCode ? ` · ${message.providerErrorCode}` : ''}
            </span>
          ) : null}
          {failed && onRetry ? (
            <Button variant="ghost" className="h-7" onClick={onRetry}>
              Retry
            </Button>
          ) : null}
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Write `GuestPanel.tsx`**

Sections in the §5.2 order. Panel headings use the mockups' `.panel-h`: `text-xs font-bold uppercase tracking-[0.1em] text-text3`.

```tsx
import { Link } from 'react-router-dom'
import type { ConversationDetail } from '../../api/types'
import { Badge } from '../../components/ui'

const CONSENT: Record<string, { tone: 'ok' | 'danger' | 'neutral'; label: string }> = {
  opted_in: { tone: 'ok', label: 'Opted in' },
  opted_out: { tone: 'danger', label: 'Opted out' },
  unknown: { tone: 'neutral', label: 'Consent unknown' },
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-border px-4 py-4">
      <h3 className="mb-2 text-xs font-bold uppercase tracking-[0.1em] text-text3">{title}</h3>
      {children}
    </section>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="text-xs text-text3">{label}</span>
      <span className="text-right text-[13px] font-semibold">{value}</span>
    </div>
  )
}

export function GuestPanel({ conversation }: { conversation: ConversationDetail }) {
  const { guest, stay, workOrders, draftPrompts, notes } = conversation
  const name = [guest.firstName, guest.lastName].filter(Boolean).join(' ') || guest.phoneE164
  const consent = CONSENT[guest.smsConsentStatus] ?? CONSENT['unknown']!
  const pending = draftPrompts.filter((p) => p.status === 'pending')

  return (
    <aside className="w-[300px] flex-none overflow-y-auto border-l border-border bg-bg2">
      <Section title="Guest">
        <p className="text-sm font-semibold">{name}</p>
        <p className="font-mono text-xs text-text3">{guest.phoneE164}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {guest.loyaltyTier ? <Badge>{guest.loyaltyTier.toUpperCase()}</Badge> : null}
          {guest.vip ? <Badge tone="warn">VIP</Badge> : null}
        </div>
      </Section>

      <Section title="Stay">
        {stay ? (
          <>
            <Field label="Room" value={[stay.roomNumber, stay.roomType].filter(Boolean).join(' · ')} />
            <Field label="Dates" value={`${stay.arrivalDate} → ${stay.departureDate}`} />
            <Field label="Party" value={`${stay.adults} adults · ${stay.children} children`} />
            <Field label="History" value={`${stay.stayCount}th stay`} />
            <Field label="Status" value={stay.status.replace('_', ' ')} />
          </>
        ) : (
          <p className="text-xs text-text3">No stay on file</p>
        )}
      </Section>

      <Section title="Consent">
        <Badge tone={consent.tone}>{consent.label}</Badge>
      </Section>

      <Section title="Work orders">
        {workOrders.length === 0 ? (
          <p className="text-xs text-text3">None</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {workOrders.map((wo) => (
              <li key={wo.id}>
                <Link
                  to={`/app/work-orders/${wo.id}`}
                  className="flex items-center justify-between gap-2 text-[13px] font-semibold hover:text-accent"
                >
                  <span className="truncate">{wo.title}</span>
                  <Badge>{wo.status.replace('_', ' ')}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Prompts">
        <p className="text-xs text-text3">
          {pending.length === 0 ? 'None pending' : `${pending.length} pending prompt${pending.length > 1 ? 's' : ''}`}
        </p>
      </Section>

      <Section title="Notes">
        {notes.length === 0 ? (
          <p className="text-xs text-text3">None</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {notes.slice(-5).map((note) => (
              <li key={note.id} className="rounded border border-noteBorder bg-noteBg p-2 text-xs text-noteText">
                {note.body}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </aside>
  )
}
```

- [ ] **Step 6: Write `ConversationHeader.tsx` and `ConversationView.tsx`**

`ConversationHeader.tsx` — presence copy comes from §5.3, with the current user excluded:

```tsx
import type { ConversationDetail } from '../../api/types'
import { useRealtime } from '../../api/ws'
import { useSession } from '../../auth/SessionContext'
import { SlaChip } from '../../components/SlaChip'
import { Badge } from '../../components/ui'

/** Exported for its own unit test — the copy is the spec (§5.3), not an implementation detail. */
export function presenceLine(names: string[], composing: boolean): string {
  const verb = composing ? 'replying' : 'viewing'
  if (names.length === 0) return ''
  if (names.length === 1) return `${names[0]} is ${verb}`
  return `${names[0]} and ${names.length - 1} other${names.length > 2 ? 's' : ''} are ${verb}`
}

export function ConversationHeader({ conversation }: { conversation: ConversationDetail }) {
  const { presence } = useRealtime()
  const { user } = useSession()
  const { guest, stay } = conversation
  const others = (presence[conversation.id] ?? []).filter((u) => u.id !== user.id)
  const composing = others.some((u) => u.state === 'composing')
  const name = [guest.firstName, guest.lastName].filter(Boolean).join(' ') || guest.phoneE164

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
      <span className="font-mono text-xl font-bold text-roomNum">{stay?.roomNumber ?? '—'}</span>
      <div className="min-w-0">
        <p className="truncate text-sm font-bold">{name}</p>
        <p className="text-xs uppercase tracking-wide text-text3">
          {[
            conversation.channelPrimary.toUpperCase(),
            guest.loyaltyTier?.toUpperCase(),
            stay ? `${stay.stayCount}TH STAY` : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </p>
      </div>
      <div className="ml-auto flex items-center gap-2">
        {others.length > 0 ? (
          <Badge tone="presence">{presenceLine(others.map((u) => u.firstName), composing)}</Badge>
        ) : null}
        {guest.smsConsentStatus === 'opted_out' ? <Badge tone="danger">Opted out</Badge> : null}
        <SlaChip
          dueAt={conversation.slaDueAt}
          startAt={conversation.lastGuestMessageAt}
          answered={!conversation.lastGuestMessageAt || Boolean(
            conversation.lastStaffMessageAt &&
              conversation.lastStaffMessageAt > conversation.lastGuestMessageAt,
          )}
        />
      </div>
    </header>
  )
}
```

`ConversationView.tsx` — owns the merged timeline and reports presence to the socket:

```tsx
import { useEffect, useMemo } from 'react'
import { useConversation } from '../../api/hooks/conversations'
import { useStaff } from '../../api/hooks/users'
import { useRealtime } from '../../api/ws'
import type { MessageOut, NoteOut } from '../../api/types'
import { EmptyState, Spinner } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { ConversationHeader } from './ConversationHeader'
import { GuestPanel } from './GuestPanel'
import { MessageBubble } from './MessageBubble'

type Entry =
  | { kind: 'message'; at: string; message: MessageOut }
  | { kind: 'note'; at: string; note: NoteOut }

export function ConversationView({ conversationId }: { conversationId: string }) {
  const { data, isPending, error } = useConversation(conversationId)
  const { data: staff } = useStaff()
  const { setPresence } = useRealtime()

  // Tell everyone else we are on this conversation; clear it on the way out.
  useEffect(() => {
    setPresence(conversationId, 'viewing')
    return () => setPresence(null, 'viewing')
  }, [conversationId, setPresence])

  const timeline = useMemo<Entry[]>(() => {
    if (!data) return []
    const entries: Entry[] = [
      // A queued message has no sentAt yet; sort it last so it appears where it was typed.
      ...data.messages.map((m) => ({ kind: 'message' as const, at: m.sentAt ?? '9999', message: m })),
      ...data.notes.map((n) => ({ kind: 'note' as const, at: n.createdAt, note: n })),
    ]
    return entries.sort((a, b) => a.at.localeCompare(b.at))
  }, [data])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !data) {
    return <EmptyState title="Could not open this conversation" hint={error?.message} />
  }

  const nameFor = (userId: string | null | undefined): string | null => {
    if (!userId) return null
    const person = staff?.find((s) => s.id === userId)
    return person?.firstName ?? null
  }

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <ConversationHeader conversation={data} />
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          {timeline.map((entry) =>
            entry.kind === 'message' ? (
              <MessageBubble
                key={entry.message.id}
                message={entry.message}
                authorName={nameFor(entry.message.authorUserId)}
              />
            ) : (
              <div
                key={entry.note.id}
                data-testid="note"
                className="rounded-card border border-noteBorder bg-noteBg px-3.5 py-3 text-sm text-noteText"
              >
                <p className="mb-1 flex items-center gap-2 text-xs font-bold uppercase tracking-wide">
                  <span className="text-noteIcon">●</span>
                  Internal
                  <span className="font-normal text-noteText/70">
                    {entry.note.authorName} · {formatClock(entry.note.createdAt)}
                  </span>
                </p>
                {entry.note.body}
              </div>
            ),
          )}
        </div>
        {/* Task 14 mounts the Composer here. */}
      </div>
      <GuestPanel conversation={data} />
    </div>
  )
}
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 8 bubble tests, 5 view tests, 5 presence-copy tests, 8 panel tests.

- [ ] **Step 8: Verify against the real server**

As Ava, open the seeded conversation for room 412: the guest's message sits left, staff replies right, the note renders amber and labelled **Internal** in time order, the panel lists the stay and the linked work order. Open the conversation the seed marks redacted — the **Card number redacted** chip shows and the body reads `**** **** **** 1234`. Open the opted-out guest's conversation — the red chip shows in both the header and the panel. Open the same conversation as `marcus@hvh.test` in a second browser profile: each header names the other within a couple of seconds.

- [ ] **Step 9: Commit**

```bash
git add web/src/features/inbox web/src/api/hooks/conversations.ts
git commit -m "feat(web): conversation thread with interleaved notes, guest panel and presence"
```

---

