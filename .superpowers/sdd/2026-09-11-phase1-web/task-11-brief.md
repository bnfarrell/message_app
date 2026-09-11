### Task 11: Realtime — one socket, backoff, query invalidation, presence

**Files:**
- Create: `web/src/api/ws.ts`
- Test: `web/src/api/ws.test.tsx`

**Interfaces:**
- Consumes: `useSession` (Task 5), `qk` (Task 3).
- Produces:
  - `RealtimeProvider({ children })` — opens exactly one socket for the active property
  - `useRealtime(): { status: 'connecting' | 'open' | 'closed'; presence: Record<string, PresenceUser[]>; setPresence: (conversationId: string | null, state: 'viewing' | 'composing') => void }`
  - `type PresenceUser = { id: string; firstName: string; avatarUrl: string | null; state: 'viewing' | 'composing' }`
  - `type ServerEvent = { type: string; propertyId: string; payload: Record<string, unknown>; at: string }`
  - `invalidationsFor(event: ServerEvent, propertyId: string): readonly unknown[][]` — exported separately so the mapping is unit-testable without a socket

**Protocol, verified in `server/app/realtime/ws.py`:**
1. Connect to `/ws` (cookie authenticates; close code `4401` means the session is dead).
2. Send `{"type":"subscribe","propertyId":…}`; the server replies `{"type":"subscribed",…}`. No events arrive before this. A property the user has no membership at closes with `4403`.
3. Send `{"type":"heartbeat"}` every 5 s — the server sweeps presence entries older than 10 s.
4. Send `{"type":"presence","conversationId":…,"state":"viewing"|"composing"}` when the open conversation or composer focus changes.

**Event → invalidation map.** Per ruling R2 there is no `typing.update`; per the contract notes, conversation events carry only `{id}`, so they invalidate rather than merge.

| Event | Invalidates |
|---|---|
| `conversation.created` | every conversation list for the property |
| `conversation.updated`, `conversation.assigned` | the lists, plus that one conversation detail |
| `message.created`, `message.status_changed` | that conversation's detail and the lists (preview and SLA change) |
| `work_order.created`, `work_order.updated` | every work-order list, that work order, and — when `sourceConversationId` is set — that conversation |
| `draft_prompt.created` | that conversation's detail and the lists |
| `notification.created` | the notification lists and the unread count |
| `presence.update` | nothing — it updates the provider's presence map |
| `subscribed` | nothing |

**Reconnect:** exponential backoff 1 s → 2 s → 4 s → 8 s → 15 s cap, with jitter. On **4401** stop retrying and let the 401 path handle it — reconnecting in a loop against a dead session is how you get a login storm. On reconnect, invalidate every property-scoped query: the client was deaf for the gap and cannot know what it missed.

- [ ] **Step 1: Write the failing test**

`web/src/api/ws.test.tsx`:

```tsx
import { act, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { qk } from './queryKeys'
import { RealtimeProvider, invalidationsFor, useRealtime } from './ws'

/** A hand-driven WebSocket: the tests decide exactly when open/message/close happen. */
class FakeSocket {
  static instances: FakeSocket[] = []
  static OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    FakeSocket.instances.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.readyState = 3
  }
  open() {
    this.readyState = 1
    this.onopen?.()
  }
  emit(event: unknown) {
    this.onmessage?.({ data: JSON.stringify(event) })
  }
  die(code = 1006) {
    this.readyState = 3
    this.onclose?.({ code })
  }
  static latest(): FakeSocket {
    return FakeSocket.instances[FakeSocket.instances.length - 1]!
  }
}

function Probe() {
  const { status, presence, setPresence } = useRealtime()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="presence">
        {(presence['c-1'] ?? []).map((u) => `${u.firstName}:${u.state}`).join(',')}
      </span>
      <button onClick={() => setPresence('c-1', 'composing')}>compose</button>
    </div>
  )
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <RealtimeProvider>
        <Probe />
      </RealtimeProvider>
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
}

describe('invalidationsFor', () => {
  const base = { propertyId: 'prop-a', at: '2026-09-10T19:00:00Z' }

  it('invalidates every list for a new conversation', () => {
    const keys = invalidationsFor(
      { ...base, type: 'conversation.created', payload: { id: 'c-1' } },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.conversationsAll('prop-a'))
  })

  it('invalidates the detail and the lists for an update', () => {
    const keys = invalidationsFor(
      { ...base, type: 'conversation.updated', payload: { id: 'c-1' } },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.conversation('prop-a', 'c-1'))
    expect(keys).toContainEqual(qk.conversationsAll('prop-a'))
  })

  it('handles conversation.assigned, which §4.5 omits but the server emits', () => {
    const keys = invalidationsFor(
      { ...base, type: 'conversation.assigned', payload: { id: 'c-1' } },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.conversation('prop-a', 'c-1'))
  })

  it('routes a message event by its conversationId, which is the payload field', () => {
    const keys = invalidationsFor(
      {
        ...base,
        type: 'message.created',
        payload: { id: 'm-1', conversationId: 'c-9', deliveryStatus: 'queued' },
      },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.conversation('prop-a', 'c-9'))
    expect(keys).toContainEqual(qk.conversationsAll('prop-a'))
  })

  it('invalidates the linked conversation for a work order raised from one', () => {
    const keys = invalidationsFor(
      {
        ...base,
        type: 'work_order.updated',
        payload: { id: 'w-1', sourceConversationId: 'c-3' },
      },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.workOrder('prop-a', 'w-1'))
    expect(keys).toContainEqual(qk.workOrdersAll('prop-a'))
    expect(keys).toContainEqual(qk.conversation('prop-a', 'c-3'))
  })

  it('leaves conversations alone for a work order with no source', () => {
    const keys = invalidationsFor(
      { ...base, type: 'work_order.created', payload: { id: 'w-2', sourceConversationId: null } },
      'prop-a',
    )
    expect(keys).not.toContainEqual(qk.conversationsAll('prop-a'))
  })

  it('invalidates the count as well as the list for a notification', () => {
    const keys = invalidationsFor(
      { ...base, type: 'notification.created', payload: { id: 'n-1' } },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.notificationsAll('prop-a'))
    expect(keys).toContainEqual(qk.unreadCount('prop-a'))
  })

  it('invalidates the conversation for a draft prompt', () => {
    const keys = invalidationsFor(
      {
        ...base,
        type: 'draft_prompt.created',
        payload: { id: 'd-1', conversationId: 'c-4', workOrderId: 'w-1', body: 'x' },
      },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.conversation('prop-a', 'c-4'))
  })

  it('invalidates nothing for presence or the subscribe acknowledgement', () => {
    expect(
      invalidationsFor({ ...base, type: 'presence.update', payload: { conversationId: 'c-1' } }, 'prop-a'),
    ).toHaveLength(0)
    expect(invalidationsFor({ ...base, type: 'subscribed', payload: {} }, 'prop-a')).toHaveLength(0)
  })

  it('ignores an event for another property', () => {
    expect(
      invalidationsFor(
        { ...base, propertyId: 'prop-b', type: 'conversation.created', payload: { id: 'c-1' } },
        'prop-a',
      ),
    ).toHaveLength(0)
  })
})

describe('RealtimeProvider', () => {
  beforeEach(() => {
    FakeSocket.instances = []
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('opens exactly one socket', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    expect(FakeSocket.latest().url).toContain('/ws')
  })

  it('subscribes to the active property as soon as the socket opens', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    expect(JSON.parse(FakeSocket.latest().sent[0]!)).toEqual({
      type: 'subscribe',
      propertyId: 'prop-a',
    })
  })

  it('reports open only after the server acknowledges the subscription', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    expect(screen.getByTestId('status')).toHaveTextContent('connecting')
    act(() =>
      FakeSocket.latest().emit({ type: 'subscribed', propertyId: 'prop-a', at: 'x', payload: {} }),
    )
    expect(screen.getByTestId('status')).toHaveTextContent('open')
  })

  it('heartbeats every 5 seconds', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() => vi.advanceTimersByTime(11_000))
    const beats = FakeSocket.latest().sent.filter((s) => s.includes('heartbeat'))
    expect(beats.length).toBeGreaterThanOrEqual(2)
  })

  it('tracks presence per conversation from presence.update', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() =>
      FakeSocket.latest().emit({
        type: 'presence.update',
        propertyId: 'prop-a',
        at: 'x',
        payload: {
          conversationId: 'c-1',
          users: [{ id: 'u-m', firstName: 'Marcus', avatarUrl: null, state: 'composing' }],
        },
      }),
    )
    expect(screen.getByTestId('presence')).toHaveTextContent('Marcus:composing')
  })

  it('replaces a conversation presence list rather than appending to it', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    const send = (users: unknown[]) =>
      act(() =>
        FakeSocket.latest().emit({
          type: 'presence.update',
          propertyId: 'prop-a',
          at: 'x',
          payload: { conversationId: 'c-1', users },
        }),
      )
    send([{ id: 'u-m', firstName: 'Marcus', avatarUrl: null, state: 'viewing' }])
    send([])
    expect(screen.getByTestId('presence')).toHaveTextContent('')
  })

  it('sends presence when a screen asks it to', async () => {
    const { getByRole } = mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() => getByRole('button', { name: 'compose' }).click())
    expect(FakeSocket.latest().sent.some((s) => s.includes('"state":"composing"'))).toBe(true)
  })

  it('invalidates queries when an event arrives', async () => {
    const { client } = mount()
    const spy = vi.spyOn(client, 'invalidateQueries')
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() =>
      FakeSocket.latest().emit({
        type: 'conversation.created',
        propertyId: 'prop-a',
        at: 'x',
        payload: { id: 'c-1' },
      }),
    )
    expect(spy).toHaveBeenCalled()
  })

  it('reconnects with backoff after an unexpected close', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() => FakeSocket.latest().die(1006))
    expect(screen.getByTestId('status')).toHaveTextContent('closed')
    act(() => vi.advanceTimersByTime(2000))
    await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThanOrEqual(2))
  })

  it('does not reconnect after 4401 — a dead session must not become a retry loop', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() => FakeSocket.latest().die(4401))
    act(() => vi.advanceTimersByTime(60_000))
    expect(FakeSocket.instances).toHaveLength(1)
  })

  it('refetches everything on reconnect, because it was deaf for the gap', async () => {
    const { client } = mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() => FakeSocket.latest().die(1006))
    const spy = vi.spyOn(client, 'invalidateQueries')
    act(() => vi.advanceTimersByTime(2000))
    await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThanOrEqual(2))
    act(() => FakeSocket.latest().open())
    act(() =>
      FakeSocket.latest().emit({ type: 'subscribed', propertyId: 'prop-a', at: 'x', payload: {} }),
    )
    expect(spy).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && npx vitest run src/api/ws.test.tsx
```

Expected: FAIL — cannot resolve `./ws`.

- [ ] **Step 3: Write `web/src/api/ws.ts`**

```ts
import { useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useSession } from '../auth/SessionContext'
import { qk } from './queryKeys'

export type PresenceUser = {
  id: string
  firstName: string
  avatarUrl: string | null
  state: 'viewing' | 'composing'
}

export type ServerEvent = {
  type: string
  propertyId: string
  payload: Record<string, unknown>
  at: string
}

const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000] as const
const HEARTBEAT_MS = 5000

function str(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

/**
 * Which query keys an event makes stale. Exported so the mapping is testable
 * without a socket — it is the part most likely to drift as events are added.
 */
export function invalidationsFor(event: ServerEvent, propertyId: string): readonly unknown[][] {
  if (event.propertyId !== propertyId) return []
  const keys: unknown[][] = []
  const id = str(event.payload['id'])
  const conversationId = str(event.payload['conversationId'])
  const sourceConversationId = str(event.payload['sourceConversationId'])

  switch (event.type) {
    case 'conversation.created':
      keys.push([...qk.conversationsAll(propertyId)])
      break
    case 'conversation.updated':
    case 'conversation.assigned':
      keys.push([...qk.conversationsAll(propertyId)])
      if (id) keys.push([...qk.conversation(propertyId, id)])
      break
    case 'message.created':
    case 'message.status_changed':
      // These payloads are full MessageOut models, so the conversation is `conversationId`.
      if (conversationId) keys.push([...qk.conversation(propertyId, conversationId)])
      keys.push([...qk.conversationsAll(propertyId)])
      break
    case 'work_order.created':
    case 'work_order.updated':
      keys.push([...qk.workOrdersAll(propertyId)])
      if (id) keys.push([...qk.workOrder(propertyId, id)])
      if (sourceConversationId) {
        keys.push([...qk.conversation(propertyId, sourceConversationId)])
        keys.push([...qk.conversationsAll(propertyId)])
      }
      break
    case 'draft_prompt.created':
      if (conversationId) keys.push([...qk.conversation(propertyId, conversationId)])
      keys.push([...qk.conversationsAll(propertyId)])
      break
    case 'notification.created':
      keys.push([...qk.notificationsAll(propertyId)])
      keys.push([...qk.unreadCount(propertyId)])
      break
    default:
      break
  }
  return keys
}

type RealtimeValue = {
  status: 'connecting' | 'open' | 'closed'
  presence: Record<string, PresenceUser[]>
  setPresence: (conversationId: string | null, state: 'viewing' | 'composing') => void
}

const RealtimeContext = createContext<RealtimeValue>({
  status: 'closed',
  presence: {},
  setPresence: () => {},
})

export function useRealtime(): RealtimeValue {
  return useContext(RealtimeContext)
}

function wsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  const [status, setStatus] = useState<'connecting' | 'open' | 'closed'>('connecting')
  const [presence, setPresenceMap] = useState<Record<string, PresenceUser[]>>({})

  const socket = useRef<WebSocket | null>(null)
  const attempt = useRef(0)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hadConnection = useRef(false)
  // The screen's current presence, replayed after a reconnect.
  const lastPresence = useRef<{ conversationId: string | null; state: 'viewing' | 'composing' }>({
    conversationId: null,
    state: 'viewing',
  })

  const send = useCallback((frame: unknown) => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify(frame))
    }
  }, [])

  const setPresence = useCallback(
    (conversationId: string | null, state: 'viewing' | 'composing') => {
      lastPresence.current = { conversationId, state }
      if (conversationId) send({ type: 'presence', conversationId, state })
    },
    [send],
  )

  useEffect(() => {
    let disposed = false
    setPresenceMap({})

    function connect() {
      if (disposed) return
      setStatus('connecting')
      const ws = new WebSocket(wsUrl())
      socket.current = ws

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'subscribe', propertyId }))
        if (lastPresence.current.conversationId) {
          ws.send(JSON.stringify({ type: 'presence', ...lastPresence.current }))
        }
      }

      ws.onmessage = (raw: MessageEvent) => {
        let event: ServerEvent
        try {
          event = JSON.parse(String(raw.data)) as ServerEvent
        } catch {
          return
        }

        if (event.type === 'subscribed') {
          setStatus('open')
          attempt.current = 0
          if (hadConnection.current) {
            // We were deaf between sockets and cannot know what changed. Refetch all of it.
            void client.invalidateQueries()
          }
          hadConnection.current = true
          return
        }

        if (event.type === 'presence.update') {
          const conversationId = str(event.payload['conversationId'])
          const users = event.payload['users']
          if (conversationId && Array.isArray(users)) {
            // Replace, never merge: the server sends the whole list for that conversation.
            setPresenceMap((current) => ({ ...current, [conversationId]: users as PresenceUser[] }))
          }
          return
        }

        for (const key of invalidationsFor(event, propertyId)) {
          void client.invalidateQueries({ queryKey: key })
        }
      }

      ws.onclose = (event: CloseEvent) => {
        setStatus('closed')
        if (disposed) return
        // 4401 = the session is gone. The 401 path owns that; retrying is a login storm.
        if (event.code === 4401 || event.code === 4403) return
        const delay = BACKOFF_MS[Math.min(attempt.current, BACKOFF_MS.length - 1)]!
        attempt.current += 1
        retryTimer.current = setTimeout(connect, delay + Math.random() * 250)
      }
    }

    connect()

    const beat = setInterval(() => send({ type: 'heartbeat' }), HEARTBEAT_MS)

    return () => {
      disposed = true
      clearInterval(beat)
      if (retryTimer.current) clearTimeout(retryTimer.current)
      socket.current?.close()
      socket.current = null
    }
  }, [propertyId, client, send])

  const value = useMemo<RealtimeValue>(
    () => ({ status, presence, setPresence }),
    [status, presence, setPresence],
  )

  return createElement(RealtimeContext.Provider, { value }, children)
}
```

`ws.ts` uses `createElement` rather than JSX so the file can stay a `.ts` module alongside the rest of `api/`.

- [ ] **Step 4: Add `RealtimeProvider` to `AppLayout`**

It belongs inside the session (it needs `propertyId`) and outside every screen (one socket for all of them):

```tsx
import { Outlet } from 'react-router-dom'
import { RealtimeProvider } from './api/ws'
import { AppShell } from './components/AppShell'
import { ThemeProvider } from './theme/ThemeContext'

export function AppLayout() {
  return (
    <ThemeProvider>
      <RealtimeProvider>
        <AppShell>
          <Outlet />
        </AppShell>
      </RealtimeProvider>
    </ThemeProvider>
  )
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 11 `invalidationsFor` tests and 11 provider tests.

- [ ] **Step 6: Verify against the real server**

With the server and `npm run web` running, sign in as Ava and open devtools → Network → WS. Confirm one `/ws` connection, a `subscribe` frame followed by `subscribed`, and a `heartbeat` every 5 s. Then stop the Flask server: the socket closes and reconnect attempts space out (1 s, 2 s, 4 s…). Restart it: the socket reopens and a burst of refetches follows.

- [ ] **Step 7: Commit**

```bash
git add web/src/api/ws.ts web/src/api/ws.test.tsx web/src/AppLayout.tsx
git commit -m "feat(web): single realtime socket with backoff, event invalidation and presence"
```

---

