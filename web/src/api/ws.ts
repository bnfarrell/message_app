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
    case 'staff_conversation.created':
    case 'staff_conversation.updated':
      keys.push([...qk.staffConversationsAll(propertyId)])
      if (id) keys.push([...qk.staffConversation(propertyId, id)])
      break
    case 'staff_message.created':
      if (conversationId) keys.push([...qk.staffConversation(propertyId, conversationId)])
      keys.push([...qk.staffConversationsAll(propertyId)])
      break
    case 'log.entry.created':
      keys.push([...qk.logFeedAll(propertyId)])
      break
    case 'log.entry.updated':
      keys.push([...qk.logFeedAll(propertyId)])
      if (id) keys.push([...qk.logEntry(propertyId, id)])
      break
    case 'pm.run.changed':
      keys.push([...qk.pmSweepAll(propertyId)])
      keys.push([...qk.pmInspectionsAll(propertyId)])
      if (id) keys.push([...qk.pmRun(propertyId, id)])
      break
    case 'pm.cycle.rolled':
      keys.push([...qk.pmSweepAll(propertyId)])
      keys.push([...qk.pmCyclesAll(propertyId)])
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
      // A null conversationId is the CLEAR, and it has to go on the wire like any other:
      // the server pops the entry and broadcasts the previous conversation's new list.
      // Guarding this on a truthy id left the entry alive until the socket died.
      send({ type: 'presence', conversationId, state })
    },
    [send],
  )

  useEffect(() => {
    let disposed = false
    setPresenceMap({})
    attempt.current = 0

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
        // An abandoned socket (superseded by a property switch or a fresh reconnect) can
        // still deliver a queued message after socket.current has moved on. Only the live
        // socket's events are ours to act on — an abandoned one's presence.update would
        // otherwise write into the new property's presence map with no property check at all.
        if (socket.current !== ws) return

        let event: ServerEvent
        try {
          event = JSON.parse(String(raw.data)) as ServerEvent
        } catch {
          return
        }

        if (event.type === 'subscribed') {
          setStatus('open')
          // attempt > 0 means this connect() followed a close — i.e. this socket is a
          // reconnect, not the initial one from mount. The prior socket (acked or not)
          // left a gap we cannot know the contents of, so refetch everything.
          const isReconnect = attempt.current > 0
          attempt.current = 0
          if (isReconnect) {
            void client.invalidateQueries()
          }
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
        // Identity, not `disposed`, is the real question: is this still the socket we're
        // reporting status for? A socket abandoned by a property switch (superseded by a
        // new one, still live) can complete its close handshake late; without this guard
        // that late event would stamp `status: 'closed'` over an already-open connection.
        if (socket.current !== ws) return
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
      // Null the ref before closing so that even a synchronously-firing close (a fake
      // socket in tests; some real implementations queue it as a same-tick microtask)
      // sees a mismatch against the identity guards above and no-ops, rather than racing
      // a state update into a component that's mid-unmount or already showing a new socket.
      const current = socket.current
      socket.current = null
      current?.close()
    }
  }, [propertyId, client, send])

  const value = useMemo<RealtimeValue>(
    () => ({ status, presence, setPresence }),
    [status, presence, setPresence],
  )

  return createElement(RealtimeContext.Provider, { value }, children)
}
