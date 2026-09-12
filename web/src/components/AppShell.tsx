import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useSession } from '../auth/SessionContext'
import { landingPath } from '../auth/capabilities'
import { useTheme } from '../theme/ThemeContext'
import { cn } from '../lib/cn'
import { useMediaQuery } from '../lib/useMediaQuery'
import { Avatar, Badge, Dropdown } from './ui'
import { NavIcon } from './NavIcon'
import { CommandPalette } from './CommandPalette'
import { MobileNav } from './MobileNav'
import { isNavItemActive, visibleNavGroups } from './navModel'

const ROLE_LABELS: Record<string, string> = {
  agent: 'Agent',
  dept_staff: 'Staff',
  supervisor: 'Supervisor',
  manager: 'Duty manager',
  admin: 'Admin',
  corporate: 'Corporate',
}

const RAIL_ITEM = 'flex h-11 items-center gap-3 rounded-md px-3 text-[13px] font-semibold'
const TOPBAR_BUTTON =
  'inline-flex h-8 flex-none items-center gap-2 rounded-md border border-border3 bg-bg2 px-2.5 text-xs font-semibold text-text3 hover:text-text'

export function AppShell({
  children,
  unreadCount,
}: {
  children: ReactNode
  unreadCount?: number
}) {
  const { user, membership, memberships, role, can, setPropertyId, logout } = useSession()
  const { resolved, setTheme } = useTheme()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // Below this width the rail (built for a mouse and 208px of spare width) stops fitting: it
  // is swapped for MobileNav's bottom bar rather than squeezed, matching the md breakpoint
  // every other responsive screen in this app (Inbox, Board, GuestPanel) already keys off.
  const isMobile = useMediaQuery('(max-width: 767px)')

  const groups = visibleNavGroups(can)
  const nextTheme = resolved === 'dark' ? 'light' : 'dark'

  // Ruling D64: tenant identity carries the switcher. Single-membership users get no
  // switcher affordance at all — the lockup is then plain text, not a dead button.
  const lockup = (
    <>
      <span className="grid h-8 w-8 flex-none place-items-center rounded-md bg-navActiveBg font-mono text-xs font-bold text-navActiveText">
        {membership.propertyCode.slice(0, 2).toUpperCase()}
      </span>
      <span className="min-w-0 text-left">
        <span className="block truncate text-[13px] font-bold text-navText">
          {membership.propertyName}
        </span>
        <span className="block truncate font-mono text-[11px] text-navTextMuted">
          {membership.propertyCode}
        </span>
      </span>
    </>
  )

  const propertySwitcher = memberships.length > 1 ? (
    <Dropdown
      triggerClassName="flex w-full items-center gap-2.5 rounded-md px-1 py-1 text-left hover:bg-navBorder"
      label={
        <>
          {lockup}
          <span className="sr-only">Switch property</span>
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            className="ml-auto h-3.5 w-3.5 flex-none text-navTextMuted"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m7 10 5 5 5-5" />
          </svg>
        </>
      }
    >
      {(close) => (
        <>
          {memberships.map((m) => (
            <button
              key={m.propertyId}
              role="menuitem"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface2"
              onClick={() => {
                close()
                setPropertyId(m.propertyId)
                // The new property's role may differ; land where it belongs.
                navigate(landingPath(m.role), { replace: true })
              }}
            >
              <span className="font-mono text-xs text-roomNum">{m.propertyCode}</span>
              <span className="truncate">{m.propertyName}</span>
            </button>
          ))}
        </>
      )}
    </Dropdown>
  ) : (
    <div className="flex items-center gap-2.5 px-1 py-1">{lockup}</div>
  )

  return (
    <div className="flex h-full flex-col bg-bg md:flex-row">
      {isMobile ? null : (
        <nav
          data-nav-surface="true"
          className="flex w-[208px] flex-none flex-col border-r border-navBorder bg-nav p-3"
        >
          <div className="mb-3 px-1">
            <span className="text-sm font-bold tracking-tight text-navTextMuted">Relay</span>
          </div>

          {propertySwitcher}

          <div className="mt-5 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto">
            {groups.map((group) => (
              <div key={group.heading}>
                <p className="mb-1 px-3 text-[10px] font-bold uppercase tracking-[0.12em] text-navSection">
                  {group.heading}
                </p>
                <ul className="flex flex-col gap-0.5">
                  {group.items.map((item) => (
                    <li key={item.to}>
                      <Link
                        to={item.to}
                        aria-current={isNavItemActive(item, pathname) ? 'page' : undefined}
                        className={cn(
                          RAIL_ITEM,
                          isNavItemActive(item, pathname)
                            ? 'bg-navActiveBg text-navActiveText'
                            : 'text-navTextMuted hover:text-navText',
                        )}
                      >
                        <NavIcon name={item.icon} />
                        <span className="flex-1">{item.label}</span>
                        {item.to === '/app/notifications' && unreadCount ? (
                          <Badge tone="danger" className="font-mono">
                            <span data-testid="unread-badge">{unreadCount}</span>
                          </Badge>
                        ) : null}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </nav>
      )}

      {/* min-h-0 undoes the flex default (min-height:auto on the main axis) that would
          otherwise let this column's content push it — and MobileNav below it — taller
          than the viewport once the outer flex switches to column direction on mobile;
          min-w-0 is the same fix for the desktop row direction. */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/*
          Three tracks. The two `1fr` side tracks are equal by definition, so the middle track
          is centred in the header at every width with no breakpoint and no dependence on how
          wide the right-hand group happens to be — and grid tracks cannot overlap, so a long
          signed-in name truncates (it carries min-w-0) instead of colliding with the search
          field. The previous absolute centring could not be pushed by its siblings: its only
          protection was arithmetic clearance measured against one particular user's name.

          Each side track is `1fr` with its automatic (min-content) floor, so the right-hand
          group can never be squeezed below its own controls; the middle track is
          `minmax(0, <width>)`, so it is the one that gives way when the bar runs short. Both
          side groups are `w-full` inside their tracks rather than shrink-to-fit, because a
          `justify-self-end` item is only clamped to its track when it is told to fill it —
          without that a long name overflowed its track leftwards and collided anyway, which
          this layout was measured doing before the `w-full` went on.

          The left track is left empty on purpose: the screens carry their own headers, and
          inventing breadcrumbs here would duplicate them.
        */}
        <header className="grid h-12 flex-none grid-cols-[1fr_minmax(0,2.25rem)_1fr] items-center gap-2 border-b border-border bg-surface px-3 sm:grid-cols-[1fr_minmax(0,260px)_1fr] lg:grid-cols-[1fr_minmax(0,340px)_1fr] 2xl:grid-cols-[1fr_minmax(0,420px)_1fr]">
          {/* The rail's own lockup carries property identity at md+; below that the rail is
              gone entirely (MobileNav replaces it), so this slot is its only remaining home. */}
          <span className="min-w-0">{isMobile ? propertySwitcher : null}</span>

          <span className="w-full min-w-0">
            <CommandPalette />
          </span>

          <span className="flex w-full min-w-0 items-center justify-end gap-2">
            <Avatar name={`${user.firstName} ${user.lastName}`} tone="accent" />
            <span className="hidden min-w-0 leading-tight md:block">
              <span className="block truncate text-xs font-semibold">
                {user.firstName} {user.lastName}
              </span>
              <span className="block truncate text-[11px] text-text3">
                {ROLE_LABELS[role] ?? role}
              </span>
            </span>

            <button
              type="button"
              aria-label={`Switch theme to ${nextTheme}`}
              onClick={() => setTheme(nextTheme)}
              className={TOPBAR_BUTTON}
            >
              <NavIcon name="theme" className="h-3.5 w-3.5" />
              <span className="hidden sm:inline capitalize">{nextTheme}</span>
            </button>

            <button
              type="button"
              aria-label="Sign out"
              onClick={() => logout()}
              className={TOPBAR_BUTTON}
            >
              <NavIcon name="signout" className="h-3.5 w-3.5" />
              <span className="hidden sm:inline" aria-hidden="true">
                Sign out
              </span>
            </button>
          </span>
        </header>

        <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
      </div>

      {isMobile ? <MobileNav groups={groups} unreadCount={unreadCount} /> : null}
    </div>
  )
}
