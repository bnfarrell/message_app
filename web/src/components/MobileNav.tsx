import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Badge } from './ui'
import { NavIcon } from './NavIcon'
import { isNavItemActive, type NavGroup } from './navModel'

const TAB = 'flex h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold'

export function MobileNav({ groups, unreadCount }: { groups: NavGroup[]; unreadCount?: number }) {
  const { pathname } = useLocation()
  const [moreOpen, setMoreOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  // The rail's first section (Overview: Inbox, Board, Alerts) is small enough to live as
  // direct tabs; everything past it (Insights, Admin) is the rarer case on a phone and
  // folds under "More" rather than crowding a bottom bar meant to stay one-tap.
  const [primary, ...overflowGroups] = groups
  const overflowItems = overflowGroups.flatMap((group) => group.items)
  const hasOverflow = overflowItems.length > 0
  const moreActive = overflowItems.some((item) => isNavItemActive(item, pathname))

  useEffect(() => {
    if (!moreOpen) return
    function onDocumentClick(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setMoreOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMoreOpen(false)
    }
    document.addEventListener('mousedown', onDocumentClick)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocumentClick)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [moreOpen])

  return (
    <div ref={root} data-nav-surface="true" className="relative flex-none border-t border-navBorder bg-nav">
      {moreOpen ? (
        <div
          role="menu"
          className="absolute inset-x-0 bottom-full border-t border-navBorder bg-nav py-1"
        >
          {overflowGroups.map((group) => (
            <div key={group.heading}>
              <p className="px-4 pt-2 text-[10px] font-bold uppercase tracking-[0.12em] text-navSection">
                {group.heading}
              </p>
              {group.items.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  role="menuitem"
                  aria-current={isNavItemActive(item, pathname) ? 'page' : undefined}
                  onClick={() => setMoreOpen(false)}
                  className="flex items-center gap-3 px-4 py-2.5 text-sm font-semibold text-navTextMuted aria-[current=page]:text-navActiveText"
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </Link>
              ))}
            </div>
          ))}
        </div>
      ) : null}

      <nav className="flex">
        {(primary?.items ?? []).map((item) => (
          <Link
            key={item.to}
            to={item.to}
            aria-current={isNavItemActive(item, pathname) ? 'page' : undefined}
            className={`${TAB} text-navTextMuted aria-[current=page]:text-navActiveText`}
          >
            <span className="relative">
              <NavIcon name={item.icon} />
              {item.to === '/app/notifications' && unreadCount ? (
                <Badge tone="danger" className="absolute -right-2 -top-1.5 font-mono">
                  <span data-testid="unread-badge">{unreadCount}</span>
                </Badge>
              ) : null}
            </span>
            {item.label}
          </Link>
        ))}
        {hasOverflow ? (
          <button
            type="button"
            aria-current={moreActive ? 'page' : undefined}
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen((v) => !v)}
            className={`${TAB} text-navTextMuted aria-[current=page]:text-navActiveText`}
          >
            <NavIcon name="admin" />
            More
          </button>
        ) : null}
      </nav>
    </div>
  )
}
