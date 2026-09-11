### Task 20: Phone simulator (dev only)

**Files:**
- Create: `web/src/features/sim/SimulatorPage.tsx`, `PhoneFrame.tsx`, `GuestPicker.tsx`, `ServerLog.tsx`
- Create: `web/src/api/hooks/sim.ts`
- Test: `web/src/features/sim/SimulatorPage.test.tsx`

**Interfaces:**
- Consumes: `api` / `qk` (Task 3), primitives (Task 4).
- Produces: `useSimGuests()`, `useSimThread(propertyId, phone)`, `useSimEvents(since)`, `useSendInbound()`; `SimulatorPage` as a **default export** (Task 8's route lazy-imports it).

**`/sim` is outside the app shell and needs no session.** The dev endpoints are unauthenticated (`server/app/api/dev.py` has no `@require_auth`) and only registered when `FLASK_ENV != production`. The page therefore does **not** use `useSession`, and must not — mounting it under `RequireAuth` would make the simulator require a login to simulate a guest who has none.

**Endpoints, exactly as the server has them:**
- `GET /api/dev/sim/guests` → `SimGuest[]` (`propertyId`, `propertyName`, `propertySmsNumber`, `guestId`, `name`, `phone`, `roomNumber`, `inHouse`, `smsConsentStatus`, `willFail`)
- `GET /api/dev/sim/thread?phone=&propertyId=` → `GuestThread` — **both params are required** (ruling R5)
- `GET /api/dev/sim/events?since=` → `SimEvent[]`
- `POST /api/hooks/sms/inbound` — **form-encoded**, Twilio field names `From`, `To`, `Body`, `MessageSid`, with header `X-Mock-Secret: dev` (the value of `MOCK_SMS_SECRET`; `mock_sms.py:47` compares it with `hmac.compare_digest`)

**The inbound POST is the one request that is not JSON.** It bypasses `api()`'s `json` option and uses `body: new URLSearchParams(...)`, which the browser sends as `application/x-www-form-urlencoded`. `request.form.to_dict()` on the server reads exactly that. Sending JSON here would still parse (the route falls back to `get_json`), but form-encoding is what a real Twilio webhook does, and the point of this screen is to be indistinguishable from one.

**Layout from `Simulator.dc.html`**, three columns:
1. **Be a guest** — a phone input plus the seeded guest list. Each row: initials avatar, name, `phone · room · in-house`, and a status `Badge` — `OPTED IN` ok, `OPTED OUT` danger, `UNKNOWN` neutral, `FAILS` warn for a `willFail` number. The caption beneath, verbatim from the mockup: "Numbers ending in 0000 fail delivery on purpose (mock error 30007) so you can test the retry path."
2. **The phone** — an iOS-style frame. Inbound-to-hotel (the guest's own messages) are the green right-aligned `.sms-out` bubbles; the hotel's messages are the grey left-aligned `.sms-in` ones. **This inversion is the whole point and the easiest thing to get backwards:** in the phone we are the guest, so `direction: 'outbound'` (hotel → guest) renders as *received*. These two bubble colours are the only hard-coded colours in the app (`#e9e9eb`/`#111111` and `#34c759`/`#ffffff`) — they imitate a phone, not the product, so they do not theme.
3. **What the server did live** — the `SimEvent` log, polled every 2 s, newest last, each line `HH:MM:SS` in mono plus the event type and a compact payload summary.

**Quick buttons** below the input, from §5.4: `STOP`, `HELP`, `"AC is broken"` (sends "The AC in our room isn't working at all, it's really warm"), and `card number` (sends "my card is 4242 4242 4242 4242" — a Luhn-valid number, so §6's redaction actually fires and the staff inbox shows the chip). Plus **Fire PMS check-in** when the selected guest has a reserved stay, and a link to **Open staff inbox**.

A `DEV ONLY` badge sits in the header, with the line `SMS_ADAPTER=mock · posts Twilio-shaped webhooks to /api/hooks/sms/inbound`.

- [ ] **Step 1: Write `web/src/api/hooks/sim.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../client'
import { qk } from '../queryKeys'
import type { GuestThread, SimEvent, SimGuest } from '../types'

export function useSimGuests() {
  return useQuery<SimGuest[], ApiError>({
    queryKey: qk.simGuests,
    queryFn: () => api<SimGuest[]>('/api/dev/sim/guests'),
  })
}

export function useSimThread(propertyId: string | undefined, phone: string | undefined) {
  return useQuery<GuestThread, ApiError>({
    queryKey: qk.simThread(propertyId ?? '', phone ?? ''),
    // Ruling R5: the server requires both params.
    queryFn: () =>
      api<GuestThread>(
        `/api/dev/sim/thread?phone=${encodeURIComponent(phone!)}&propertyId=${encodeURIComponent(propertyId!)}`,
      ),
    enabled: Boolean(propertyId && phone),
    // The simulator has no socket of its own; a 2s poll is simpler and dev-only.
    refetchInterval: 2000,
  })
}

export function useSimEvents() {
  return useQuery<SimEvent[], ApiError>({
    queryKey: qk.simEvents,
    queryFn: () => api<SimEvent[]>('/api/dev/sim/events'),
    refetchInterval: 2000,
  })
}

export function useSendInbound() {
  const client = useQueryClient()
  return useMutation<void, ApiError, { from: string; to: string; body: string }>({
    mutationFn: ({ from, to, body }) =>
      // Form-encoded with Twilio's field names, exactly as a real webhook arrives.
      api<void>('/api/hooks/sms/inbound', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Mock-Secret': 'dev',
        },
        body: new URLSearchParams({
          From: from,
          To: to,
          Body: body,
          MessageSid: `mock-${Math.random().toString(16).slice(2, 10)}`,
        }),
      } as never),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['sim'] })
    },
  })
}
```

`api()`'s `ApiInit` omits `body`, so `useSendInbound` needs it back. Widen the type rather than casting — in `client.ts`, change:

```ts
export type ApiInit = Omit<RequestInit, 'body'> & { json?: unknown; body?: BodyInit }
```

and in `api()`, use the explicit body when `json` is absent:

```ts
      body: json === undefined ? (rest as { body?: BodyInit }).body : JSON.stringify(json),
```

Destructure `body` out of `rest` first so it is not spread twice. Then drop the `as never` from the hook. **Add a client test for this:** "sends a raw body and does not set a JSON content type when `body` is used instead of `json`".

- [ ] **Step 2: Write the failing test**

`web/src/features/sim/SimulatorPage.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../../test/harness'
import SimulatorPage from './SimulatorPage'

const GUESTS = [
  {
    propertyId: 'prop-a', propertyName: 'Harbourview Hotel', propertySmsNumber: '+15550100',
    guestId: 'g-1', name: 'Sarah Chen', phone: '+15551234567', roomNumber: '412',
    inHouse: true, smsConsentStatus: 'opted_in', willFail: false,
  },
  {
    propertyId: 'prop-a', propertyName: 'Harbourview Hotel', propertySmsNumber: '+15550100',
    guestId: 'g-2', name: 'Tom Becker', phone: '+15552000000', roomNumber: '516',
    inHouse: true, smsConsentStatus: 'opted_in', willFail: true,
  },
  {
    propertyId: 'prop-a', propertyName: 'Harbourview Hotel', propertySmsNumber: '+15550100',
    guestId: 'g-3', name: 'Lena Park', phone: '+15553104411', roomNumber: null,
    inHouse: false, smsConsentStatus: 'opted_out', willFail: false,
  },
]

const THREAD = {
  phone: '+15551234567',
  propertyName: 'Harbourview Hotel',
  messages: [
    { id: 'm1', direction: 'outbound', body: 'Welcome to Harbourview, Sarah.', deliveryStatus: 'delivered', sentAt: '2026-09-10T15:22:00Z' },
    { id: 'm2', direction: 'inbound', body: 'Hi, the AC is not working', deliveryStatus: 'delivered', sentAt: '2026-09-10T18:41:00Z' },
  ],
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    const body = url.includes('sim/guests')
      ? GUESTS
      : url.includes('sim/thread')
        ? THREAD
        : url.includes('sim/events')
          ? [{ type: 'message.created', propertyId: 'prop-a', at: '2026-09-10T18:41:07Z', payload: { id: 'm2' } }]
          : []
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  // No SessionProvider on purpose: /sim must work without a login.
  return renderWithProviders(<SimulatorPage />, { route: '/sim' })
}

describe('SimulatorPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders without a session', async () => {
    mount()
    expect(await screen.findByText('Phone simulator')).toBeInTheDocument()
    expect(screen.getByText('DEV ONLY')).toBeInTheDocument()
  })

  it('lists the seeded guests with room and consent state', async () => {
    mount()
    expect(await screen.findByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText(/412/)).toBeInTheDocument()
    expect(screen.getByText('OPTED OUT')).toBeInTheDocument()
  })

  it('flags a number that will fail delivery', async () => {
    mount()
    expect(await screen.findByText('FAILS')).toBeInTheDocument()
    expect(screen.getByText(/0000 fail delivery on purpose/i)).toBeInTheDocument()
  })

  it('loads a thread with both phone and propertyId (ruling R5)', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([u]) => String(u).includes('sim/thread'))
      expect(call).toBeDefined()
      expect(String(call![0])).toContain('propertyId=prop-a')
      expect(String(call![0])).toContain('phone=%2B15551234567')
    })
  })

  it('renders the hotel message as received and the guest message as sent', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    // In the phone we are the guest: outbound (hotel → guest) is the *received* bubble.
    const received = await screen.findByText('Welcome to Harbourview, Sarah.')
    const sent = screen.getByText('Hi, the AC is not working')
    expect(received.closest('[data-testid="sms-in"]')).not.toBeNull()
    expect(sent.closest('[data-testid="sms-out"]')).not.toBeNull()
  })

  it('posts form-encoded Twilio fields with the mock secret', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.type(await screen.findByPlaceholderText(/text as/i), 'Extra towels please')
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }))

    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(String(post[0])).toBe('/api/hooks/sms/inbound')
    const headers = new Headers(post[1]!.headers)
    expect(headers.get('X-Mock-Secret')).toBe('dev')
    const params = new URLSearchParams(String(post[1]!.body))
    expect(params.get('From')).toBe('+15551234567')
    expect(params.get('To')).toBe('+15550100')
    expect(params.get('Body')).toBe('Extra towels please')
    expect(params.get('MessageSid')).toBeTruthy()
  })

  it('sends STOP from the quick button', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(await screen.findByRole('button', { name: 'STOP' }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(new URLSearchParams(String(post[1]!.body)).get('Body')).toBe('STOP')
  })

  it('sends a Luhn-valid card number so redaction actually fires', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(await screen.findByRole('button', { name: /card number/i }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')!
    const sent = new URLSearchParams(String(post[1]!.body)).get('Body')!
    const digits = sent.replace(/\D/g, '')
    // Luhn check — if this fails the server will not redact and the demo is silently broken.
    let sum = 0
    let double = false
    for (let i = digits.length - 1; i >= 0; i--) {
      let d = Number(digits[i])
      if (double) {
        d *= 2
        if (d > 9) d -= 9
      }
      sum += d
      double = !double
    }
    expect(digits.length).toBeGreaterThanOrEqual(13)
    expect(sum % 10).toBe(0)
  })

  it('will not send with no guest selected', async () => {
    mount()
    await screen.findByText('Sarah Chen')
    expect(screen.getByRole('button', { name: /^send$/i })).toBeDisabled()
  })

  it('will not send an empty message', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }))
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })

  it('shows the server event log', async () => {
    mount()
    expect(await screen.findByText(/message\.created/)).toBeInTheDocument()
  })

  it('links to the staff inbox', async () => {
    mount()
    expect(await screen.findByRole('link', { name: /open staff inbox/i })).toHaveAttribute(
      'href',
      '/app/inbox',
    )
  })
})
```

- [ ] **Step 3: Write `PhoneFrame.tsx`**

```tsx
import type { GuestThread } from '../../api/types'
import { formatClock } from '../../lib/time'

/**
 * These two bubble colours are hard-coded on purpose — they imitate iOS Messages,
 * not this product, so they must not follow the app theme.
 */
const RECEIVED = { background: '#e9e9eb', color: '#111111' }
const SENT = { background: '#34c759', color: '#ffffff' }

export function PhoneFrame({ thread, smsNumber }: { thread: GuestThread; smsNumber: string | null }) {
  return (
    <div className="mx-auto flex h-full w-full max-w-[380px] flex-col overflow-hidden rounded-[28px] border border-border3 bg-white">
      <header className="flex flex-col items-center gap-0.5 border-b border-[#d1d1d6] bg-[#f6f6f6] px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-[#0e1116] font-mono text-[11px] font-bold text-white">
          HV
        </span>
        <p className="text-[13px] font-semibold text-[#111111]">{thread.propertyName}</p>
        <p className="font-mono text-[11px] text-[#8e8e93]">{smsNumber ?? thread.phone}</p>
      </header>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto bg-white p-3">
        {thread.messages.length === 0 ? (
          <p className="mt-6 text-center text-xs text-[#8e8e93]">No messages yet.</p>
        ) : (
          thread.messages.map((message) => {
            // We are the guest here: the hotel's outbound message is what we received.
            const received = message.direction === 'outbound'
            return (
              <div
                key={message.id}
                data-testid={received ? 'sms-in' : 'sms-out'}
                className={`max-w-[78%] px-3 py-2 text-sm leading-snug ${
                  received
                    ? 'self-start rounded-2xl rounded-bl-sm'
                    : 'self-end rounded-2xl rounded-br-sm'
                }`}
                style={received ? RECEIVED : SENT}
              >
                {message.body}
                <span className="mt-0.5 block text-[10.5px] opacity-70">
                  {message.sentAt ? formatClock(message.sentAt) : '…'}
                  {received ? ` · ${message.deliveryStatus}` : ''}
                </span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Write `SimulatorPage.tsx`**

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useSendInbound, useSimEvents, useSimGuests, useSimThread } from '../../api/hooks/sim'
import type { SimGuest } from '../../api/types'
import { Avatar, Badge, Button, Input, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'

const CONSENT_TONE = {
  opted_in: 'ok',
  opted_out: 'danger',
  unknown: 'neutral',
} as const

// §5.4's quick buttons. The card number is Luhn-valid so §6's redaction actually fires.
const QUICK = [
  { label: 'STOP', body: 'STOP' },
  { label: 'HELP', body: 'HELP' },
  { label: '"AC is broken"', body: "The AC in our room isn't working at all, it's really warm" },
  { label: 'card number', body: 'my card is 4242 4242 4242 4242' },
]

export default function SimulatorPage() {
  const guests = useSimGuests()
  const events = useSimEvents()
  const [selected, setSelected] = useState<SimGuest | null>(null)
  const [manualPhone, setManualPhone] = useState('')
  const [draft, setDraft] = useState('')
  const send = useSendInbound()

  const thread = useSimThread(selected?.propertyId, selected?.phone)

  function post(body: string) {
    if (!selected || !body.trim()) return
    send.mutate({
      from: selected.phone,
      to: selected.propertySmsNumber ?? '',
      body: body.trim(),
    })
    setDraft('')
  }

  return (
    <div className="flex h-full flex-col bg-bg text-text">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-accent font-mono text-xs font-bold text-accentText">
          HV
        </span>
        <h1 className="text-base font-bold">Phone simulator</h1>
        <Badge tone="warn">DEV ONLY</Badge>
        <p className="text-xs text-text3">
          SMS_ADAPTER=mock · posts Twilio-shaped webhooks to /api/hooks/sms/inbound
        </p>
        <Link to="/app/inbox" className="ml-auto text-sm font-semibold text-accent hover:underline">
          Open staff inbox
        </Link>
      </header>

      <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)_360px]">
        <section className="flex min-h-0 flex-col rounded-card border border-border2 bg-surface">
          <h2 className="border-b border-border px-3.5 py-3 text-xs font-bold uppercase tracking-[0.1em] text-text3">
            Be a guest
          </h2>
          <div className="border-b border-border p-3">
            <Input
              placeholder="+1 555 … or pick below"
              value={manualPhone}
              onChange={(event) => setManualPhone(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && manualPhone.trim() && guests.data?.[0]) {
                  // An unseeded number still needs a property to post to; use the first one.
                  const template = guests.data[0]!
                  setSelected({
                    ...template,
                    guestId: 'manual',
                    name: manualPhone.trim(),
                    phone: manualPhone.trim(),
                    roomNumber: null,
                    inHouse: false,
                    smsConsentStatus: 'unknown',
                    willFail: manualPhone.trim().endsWith('0000'),
                  })
                }
              }}
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {guests.isPending ? (
              <div className="grid place-items-center p-6">
                <Spinner />
              </div>
            ) : (
              (guests.data ?? []).map((guest) => (
                <button
                  key={guest.guestId}
                  onClick={() => setSelected(guest)}
                  className={cn(
                    'flex w-full items-center gap-2.5 border-b border-border px-3.5 py-3 text-left',
                    selected?.guestId === guest.guestId
                      ? 'bg-sel shadow-[inset_3px_0_0_var(--accent)]'
                      : 'hover:bg-surface2',
                  )}
                >
                  <Avatar name={guest.name} size={32} tone="muted" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{guest.name}</span>
                    <span className="block truncate font-mono text-xs text-text3">
                      {guest.phone}
                      {guest.roomNumber ? ` · ${guest.roomNumber}` : ''}
                      {guest.inHouse ? ' · in-house' : ''}
                    </span>
                  </span>
                  <Badge tone={guest.willFail ? 'warn' : CONSENT_TONE[guest.smsConsentStatus]}>
                    {guest.willFail ? 'FAILS' : guest.smsConsentStatus.replace('_', ' ').toUpperCase()}
                  </Badge>
                </button>
              ))
            )}
          </div>
          <p className="border-t border-border p-3 text-xs text-text3">
            Numbers ending in 0000 fail delivery on purpose (mock error 30007) so you can test the
            retry path.
          </p>
        </section>

        <section className="flex min-h-0 flex-col gap-3">
          <div className="min-h-0 flex-1">
            {thread.data ? (
              <PhoneFrame thread={thread.data} smsNumber={selected?.propertySmsNumber ?? null} />
            ) : (
              <div className="grid h-full place-items-center rounded-card border border-border2 bg-surface text-sm text-text3">
                Pick a guest to see their thread.
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            {QUICK.map((quick) => (
              <button
                key={quick.label}
                disabled={!selected}
                onClick={() => post(quick.body)}
                className="inline-flex h-9 items-center rounded-full border border-border3 bg-surface px-3 text-[12.5px] font-semibold text-text2 disabled:opacity-50"
              >
                {quick.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Input
              placeholder={`Text as ${selected?.name.split(' ')[0] ?? 'guest'}…`}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') post(draft)
              }}
            />
            <Button
              variant="primary"
              disabled={!selected}
              loading={send.isPending}
              onClick={() => post(draft)}
            >
              Send
            </Button>
          </div>
          {send.error ? (
            <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
              {send.error.message}
            </p>
          ) : null}
        </section>

        <section className="flex min-h-0 flex-col rounded-card border border-border2 bg-surface">
          <h2 className="border-b border-border px-3.5 py-3 text-xs font-bold uppercase tracking-[0.1em] text-text3">
            What the server did live
          </h2>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {(events.data ?? []).length === 0 ? (
              <p className="p-3.5 text-xs text-text3">Nothing yet. Send a message.</p>
            ) : (
              (events.data ?? []).map((event, index) => (
                <div
                  key={`${event.at}-${index}`}
                  className="grid grid-cols-[72px_minmax(0,1fr)] gap-2.5 border-b border-border px-3.5 py-2 text-[12.5px]"
                >
                  <span className="font-mono text-text3">
                    {new Date(event.at).toLocaleTimeString([], { hour12: false })}
                  </span>
                  <span className="min-w-0">
                    <span className="font-semibold">{event.type}</span>
                    <span className="block truncate text-text3">
                      {Object.entries(event.payload)
                        .slice(0, 3)
                        .map(([key, value]) => `${key}=${String(value)}`)
                        .join(' · ')}
                    </span>
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
```

Import `PhoneFrame` at the top: `import { PhoneFrame } from './PhoneFrame'`.

**`GuestPicker.tsx` and `ServerLog.tsx` are not needed** — both are small enough to live inline in `SimulatorPage`, and splitting them would create two files with one caller each. Do not create them; drop them from the plan's file list.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 12 simulator tests, plus the new `client.ts` raw-body test from Step 1.

- [ ] **Step 6: Verify the whole compliance story against the real server**

Open `http://localhost:5173/sim` in one window and the staff inbox as Ava in another:
1. Pick Sarah Chen, send "The AC is broken". Her conversation appears at the top of Ava's queue within a second, SLA chip running.
2. Reply from the inbox. The green bubble appears in the phone, `Delivered` after the worker ticks.
3. Pick Tom Becker (`…0000`), and have Ava reply. It goes **Failed · 30007**; **Retry** re-queues it.
4. As Sarah, press **STOP**. Exactly **one** confirmation comes back ("You're unsubscribed…"), the staff inbox shows the red **Opted out** chip, and Ava's next send is rejected with `422` and the server's message. Press **START** and confirm she is opted back in.
5. Press **HELP** and confirm the property's help text comes back.
6. Press **card number** and confirm the staff inbox shows `**** **** **** 4242` with the **Card number redacted** chip. If it shows the raw digits, the number is not passing Luhn — that is a real bug, not a display issue.
7. Watch the right-hand log narrate each step.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/sim web/src/api/hooks/sim.ts web/src/api/client.ts web/src/api/client.test.ts
git commit -m "feat(web): phone simulator posting Twilio-shaped webhooks"
```

---

