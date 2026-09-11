### Task 18: Notifications — bell, unread count, centre

**Files:**
- Create: `web/src/api/hooks/notifications.ts`, `web/src/features/notifications/NotificationsPage.tsx`, `NotificationBell.tsx`
- Modify: `web/src/components/AppShell.tsx` (feed the real unread count), `web/src/AppLayout.tsx`, `web/src/routes.tsx`
- Test: `web/src/features/notifications/NotificationsPage.test.tsx`

**Interfaces:**
- Consumes: `api` / `qk` (Task 3), `relativeTime` (Task 10).
- Produces: `useNotifications(unreadOnly: boolean)`, `useUnreadCount()`, `useMarkRead()`, `useMarkAllRead()`; `NotificationsPage`; `NotificationBell`.

**Wiring the count into the shell.** Task 9 left `AppShell`'s `unreadCount` as a prop precisely so the shell never fetches. `AppLayout` now reads `useUnreadCount()` and passes it down. The count invalidates on `notification.created` (Task 11's map already does this), so the badge moves without a poll.

**Entity links.** `NotificationOut` carries `entityType` and `entityId`. Map `conversation` → `/app/inbox/<id>`, `work_order` → `/app/work-orders/<id>`; anything else renders as plain text with no link. Clicking a notification marks it read **and** navigates — the two are one action from the operator's point of view.

**Rows** carry an unread marker (a `bg-accent` dot), the title in `text-sm font-semibold`, the body in `text-xs text-text3`, and `relativeTime(createdAt)` in mono on the right. Unread rows sit on `bg-sel`. A **Mark all read** button sits in the header, disabled when the count is zero.

- [ ] **Step 1: Write `web/src/api/hooks/notifications.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { NotificationOut, UnreadCount } from '../types'

export function useNotifications(unreadOnly: boolean) {
  const { propertyId } = useSession()
  return useQuery<NotificationOut[], ApiError>({
    queryKey: qk.notifications(propertyId, unreadOnly),
    queryFn: () =>
      api<NotificationOut[]>(
        propertyPath(propertyId, `notifications${unreadOnly ? '?unread=1' : ''}`),
      ),
  })
}

export function useUnreadCount() {
  const { propertyId } = useSession()
  return useQuery<UnreadCount, ApiError>({
    queryKey: qk.unreadCount(propertyId),
    queryFn: () => api<UnreadCount>(propertyPath(propertyId, 'notifications/unread-count')),
    // The socket invalidates this; the interval is a backstop for a dropped connection.
    refetchInterval: 60_000,
  })
}

function useInvalidateNotifications() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: qk.notificationsAll(propertyId) })
    void client.invalidateQueries({ queryKey: qk.unreadCount(propertyId) })
  }
}

export function useMarkRead() {
  const { propertyId } = useSession()
  const invalidate = useInvalidateNotifications()
  return useMutation<void, ApiError, { id: string }>({
    mutationFn: ({ id }) =>
      api<void>(propertyPath(propertyId, `notifications/${id}/read`), { method: 'POST' }),
    onSuccess: invalidate,
  })
}

export function useMarkAllRead() {
  const { propertyId } = useSession()
  const invalidate = useInvalidateNotifications()
  return useMutation<void, ApiError, void>({
    mutationFn: () =>
      api<void>(propertyPath(propertyId, 'notifications/read-all'), { method: 'POST' }),
    onSuccess: invalidate,
  })
}
```

- [ ] **Step 2: Write the failing test**

`web/src/features/notifications/NotificationsPage.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aNotification } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { NotificationsPage } from './NotificationsPage'

function serve(rows: unknown[]) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    const body = String(input).includes('unread-count') ? { count: 2 } : rows
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
      <NotificationsPage />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: '/app/notifications' },
  )
}

describe('NotificationsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve([aNotification()])
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists notifications with their title and body', async () => {
    mount()
    expect(await screen.findByText('SLA breached in 412')).toBeInTheDocument()
    expect(screen.getByText(/waiting 16 minutes/)).toBeInTheDocument()
  })

  it('marks an unread one visually', async () => {
    mount()
    await screen.findByText('SLA breached in 412')
    expect(screen.getByTestId('unread-dot')).toBeInTheDocument()
  })

  it('does not mark a read one', async () => {
    serve([aNotification({ readAt: '2026-09-10T19:00:00Z' })])
    mount()
    await screen.findByText('SLA breached in 412')
    expect(screen.queryByTestId('unread-dot')).not.toBeInTheDocument()
  })

  it('links a conversation notification to the inbox', async () => {
    mount()
    expect(await screen.findByRole('link', { name: /SLA breached in 412/ })).toHaveAttribute(
      'href',
      '/app/inbox/c-1',
    )
  })

  it('links a work-order notification to the board detail', async () => {
    serve([aNotification({ entityType: 'work_order', entityId: 'w-204', title: 'WO assigned' })])
    mount()
    expect(await screen.findByRole('link', { name: /WO assigned/ })).toHaveAttribute(
      'href',
      '/app/work-orders/w-204',
    )
  })

  it('renders an unlinkable notification as plain text', async () => {
    serve([aNotification({ entityType: null, entityId: null, title: 'Shift handover' })])
    mount()
    await screen.findByText('Shift handover')
    expect(screen.queryByRole('link', { name: /Shift handover/ })).not.toBeInTheDocument()
  })

  it('marks a notification read when it is opened', async () => {
    mount()
    await userEvent.click(await screen.findByRole('link', { name: /SLA breached in 412/ }))
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/notifications/nt-1/read')),
      ).toBe(true),
    )
  })

  it('marks all read', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /mark all read/i }))
    expect(
      vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/notifications/read-all')),
    ).toBe(true)
  })

  it('filters to unread only', async () => {
    mount()
    await screen.findByText('SLA breached in 412')
    await userEvent.click(screen.getByRole('tab', { name: /unread/i }))
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('unread=1'))).toBe(true),
    )
  })

  it('shows an empty state when there is nothing', async () => {
    serve([])
    mount()
    expect(await screen.findByText(/nothing to catch up on/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Write `NotificationsPage.tsx`**

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  useUnreadCount,
} from '../../api/hooks/notifications'
import type { NotificationOut } from '../../api/types'
import { Button, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { relativeTime } from '../../lib/time'

function linkFor(notification: NotificationOut): string | null {
  if (!notification.entityId) return null
  if (notification.entityType === 'conversation') return `/app/inbox/${notification.entityId}`
  if (notification.entityType === 'work_order') return `/app/work-orders/${notification.entityId}`
  return null
}

export function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false)
  const { data, isPending, error } = useNotifications(unreadOnly)
  const unread = useUnreadCount()
  const markRead = useMarkRead()
  const markAll = useMarkAllRead()

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Alerts</h1>
        <div role="tablist" className="flex gap-1.5">
          {[
            { key: false, label: 'All' },
            { key: true, label: 'Unread' },
          ].map((tab) => (
            <button
              key={tab.label}
              role="tab"
              aria-selected={unreadOnly === tab.key}
              onClick={() => setUnreadOnly(tab.key)}
              className={cn(
                'inline-flex h-9 items-center rounded px-3.5 text-[13.5px] font-semibold',
                unreadOnly === tab.key ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <Button
          className="ml-auto"
          disabled={(unread.data?.count ?? 0) === 0}
          loading={markAll.isPending}
          onClick={() => markAll.mutate()}
        >
          Mark all read
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isPending ? (
          <div className="grid place-items-center p-10">
            <Spinner />
          </div>
        ) : error ? (
          <EmptyState title="Could not load alerts" hint={error.message} />
        ) : (data ?? []).length === 0 ? (
          <EmptyState title="Nothing to catch up on" hint="New alerts will appear here." />
        ) : (
          (data ?? []).map((notification) => {
            const href = linkFor(notification)
            const body = (
              <>
                <span className="flex w-4 flex-none justify-center">
                  {notification.readAt ? null : (
                    <span data-testid="unread-dot" className="h-2 w-2 rounded-full bg-accent" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{notification.title}</span>
                  {notification.body ? (
                    <span className="block text-xs text-text3">{notification.body}</span>
                  ) : null}
                </span>
                <span className="flex-none font-mono text-xs text-text3">
                  {relativeTime(notification.createdAt)}
                </span>
              </>
            )
            const className = cn(
              'flex items-center gap-3 border-b border-border px-4 py-3.5',
              notification.readAt ? 'hover:bg-surface2' : 'bg-sel',
            )
            // Opening one is also acknowledging it; two clicks for one intent is wrong.
            return href ? (
              <Link
                key={notification.id}
                to={href}
                className={className}
                onClick={() => {
                  if (!notification.readAt) markRead.mutate({ id: notification.id })
                }}
              >
                {body}
              </Link>
            ) : (
              <div key={notification.id} className={className}>
                {body}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Write `NotificationBell.tsx` and wire the count into the shell**

`NotificationBell.tsx` is the compact affordance for a future header; the nav badge is the primary one. Keep it minimal and use it from `AppLayout` only if the nav is collapsed — for Phase 1 the nav badge suffices, so export it but do not mount it. **Implementer: if nothing mounts `NotificationBell`, do not create the file** — an unused component is worse than a missing one. Instead, wire the count:

`AppLayout.tsx`:

```tsx
import { Outlet } from 'react-router-dom'
import { useUnreadCount } from './api/hooks/notifications'
import { RealtimeProvider } from './api/ws'
import { AppShell } from './components/AppShell'
import { ThemeProvider } from './theme/ThemeContext'

function Shell() {
  // The shell stays fetch-free (Task 9); the count is fed in from here.
  const unread = useUnreadCount()
  return (
    <AppShell unreadCount={unread.data?.count}>
      <Outlet />
    </AppShell>
  )
}

export function AppLayout() {
  return (
    <ThemeProvider>
      <RealtimeProvider>
        <Shell />
      </RealtimeProvider>
    </ThemeProvider>
  )
}
```

Replace the Alerts placeholder in `routes.tsx` with `<NotificationsPage />`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 11 notification tests.

- [ ] **Step 6: Verify against the real server**

As Ava, the nav **Alerts** row shows a red count from the seeded overdue conversations. Open it: rows link into the inbox, an unread row is amber-tinted with a dot, opening one clears its dot and drops the nav count. **Mark all read** empties the badge. Then, with the tab open, use the simulator (Task 20) or a second session to trigger an SLA breach — the badge increments without a reload, which is Task 11's invalidation proving itself.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/notifications web/src/api/hooks/notifications.ts web/src/AppLayout.tsx web/src/routes.tsx
git commit -m "feat(web): notification centre and live unread badge"
```

---

