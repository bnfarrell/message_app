import { act, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider, useSession } from '../auth/SessionContext'
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

/** Like Probe, but also exposes a way to switch the active property mid-test. */
function SwitchableProbe() {
  const { status } = useRealtime()
  const { setPropertyId } = useSession()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <button onClick={() => setPropertyId('prop-b')}>switch property</button>
    </div>
  )
}

function mountSwitchable() {
  return renderWithProviders(
    <SessionProvider>
      <RealtimeProvider>
        <SwitchableProbe />
      </RealtimeProvider>
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent', withSecondProperty: true }) },
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

  it('invalidates the list, and the detail when present, for a staff conversation event', () => {
    const created = invalidationsFor(
      { ...base, type: 'staff_conversation.created', payload: { id: 'sc-1' } },
      'prop-a',
    )
    expect(created).toContainEqual(qk.staffConversationsAll('prop-a'))
    expect(created).toContainEqual(qk.staffConversation('prop-a', 'sc-1'))

    const updated = invalidationsFor(
      { ...base, type: 'staff_conversation.updated', payload: { id: 'sc-2' } },
      'prop-a',
    )
    expect(updated).toContainEqual(qk.staffConversationsAll('prop-a'))
    expect(updated).toContainEqual(qk.staffConversation('prop-a', 'sc-2'))
  })

  it('routes a staff message event by its conversationId, which is the payload field', () => {
    const keys = invalidationsFor(
      { ...base, type: 'staff_message.created', payload: { conversationId: 'sc-9' } },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.staffConversation('prop-a', 'sc-9'))
    expect(keys).toContainEqual(qk.staffConversationsAll('prop-a'))
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

  it('invalidates the log feed on log.entry.created', () => {
    const keys = invalidationsFor(
      { type: 'log.entry.created', propertyId: 'p1', payload: { id: 'e1' }, at: '' },
      'p1',
    )
    expect(keys).toContainEqual(['logFeed', 'p1'])
  })

  it('invalidates both feed and entry on log.entry.updated', () => {
    const keys = invalidationsFor(
      { type: 'log.entry.updated', propertyId: 'p1', payload: { id: 'e1' }, at: '' },
      'p1',
    )
    expect(keys).toContainEqual(['logFeed', 'p1'])
    expect(keys).toContainEqual(['logEntry', 'p1', 'e1'])
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

  it('does not invalidate anything on a plain first connection', async () => {
    const { client } = mount()
    const spy = vi.spyOn(client, 'invalidateQueries')
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() =>
      FakeSocket.latest().emit({ type: 'subscribed', propertyId: 'prop-a', at: 'x', payload: {} }),
    )
    expect(spy).not.toHaveBeenCalled()
  })

  it('reconnects with backoff after an unexpected close', async () => {
    mount()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    act(() => FakeSocket.latest().open())
    act(() => FakeSocket.latest().die(1006))
    expect(screen.getByTestId('status')).toHaveTextContent('closed')
    // The first backoff step is 1000ms plus up to 250ms of jitter: nothing should have
    // reconnected yet at 900ms, but the window is guaranteed closed by 1300ms.
    act(() => vi.advanceTimersByTime(900))
    expect(FakeSocket.instances).toHaveLength(1)
    act(() => vi.advanceTimersByTime(400))
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(2))
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
    // Unscoped: a reconnect can't know what it missed, so it must invalidate everything
    // rather than some specific key — toHaveBeenCalledWith() asserts zero arguments.
    expect(spy).toHaveBeenCalledWith()
  })

  it('does not let a socket abandoned by a property switch stamp a stale close over the new one', async () => {
    mountSwitchable()
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
    const socket1 = FakeSocket.latest()
    act(() => socket1.open())
    act(() =>
      socket1.emit({ type: 'subscribed', propertyId: 'prop-a', at: 'x', payload: {} }),
    )
    expect(screen.getByTestId('status')).toHaveTextContent('open')

    // Switching property runs socket1's cleanup — which calls close() on it — and opens
    // socket2 for the new property. A real socket's close handshake doesn't complete
    // synchronously, so its resulting close event can legitimately arrive after socket2 is
    // already open and acked; `die()` drives that arrival explicitly, at exactly the moment
    // this test needs, rather than racing it against the suite's `shouldAdvanceTime` clock.
    act(() => screen.getByRole('button', { name: 'switch property' }).click())
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(2))
    const socket2 = FakeSocket.latest()
    act(() => socket2.open())
    act(() =>
      socket2.emit({ type: 'subscribed', propertyId: 'prop-b', at: 'x', payload: {} }),
    )
    expect(screen.getByTestId('status')).toHaveTextContent('open')

    // socket1's close finally arrives now — after socket2 is already open and acked for
    // the new property. It must not be able to report on a connection it no longer owns.
    act(() => socket1.die(1000))
    expect(screen.getByTestId('status')).toHaveTextContent('open')
  })
})
