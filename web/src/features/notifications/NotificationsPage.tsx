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
                'inline-flex h-11 items-center rounded px-3.5 text-[13.5px] font-semibold md:h-9',
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
