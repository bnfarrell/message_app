import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useSession } from '../auth/SessionContext'
import { landingPath } from '../auth/capabilities'
import { useTheme } from '../theme/ThemeContext'
import { cn } from '../lib/cn'
import { Avatar, Badge, Dropdown } from './ui'
import { NavIcon } from './NavIcon'
import { CommandPalette } from './CommandPalette'
import { visibleNavGroups } from './navModel'

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
  'inline-flex h-8 items-center gap-2 rounded-md border border-border3 bg-bg2 px-2.5 text-xs font-semibold text-text3 hover:text-text'

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

  return (
    <div className="flex h-full bg-bg">
      <nav
        data-nav-surface="true"
        className="flex w-[208px] flex-none flex-col border-r border-navBorder bg-nav p-3"
      >
        {memberships.length > 1 ? (
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
        )}

        <div className="mt-5 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto">
          {groups.map((group) => (
            <div key={group.heading}>
              <p className="mb-1 px-3 text-[10px] font-bold uppercase tracking-[0.12em] text-navSection">
                {group.heading}
              </p>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      className={({ isActive }) =>
                        cn(
                          RAIL_ITEM,
                          isActive
                            ? 'bg-navActiveBg text-navActiveText'
                            : 'text-navTextMuted hover:text-navText',
                        )
                      }
                    >
                      <NavIcon name={item.icon} />
                      <span className="flex-1">{item.label}</span>
                      {item.to === '/app/notifications' && unreadCount ? (
                        <Badge tone="danger" className="font-mono">
                          <span data-testid="unread-badge">{unreadCount}</span>
                        </Badge>
                      ) : null}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* The rest of the bar is left empty on purpose: the screens carry their own headers,
            and inventing breadcrumbs here would duplicate them. */}
        <header className="relative flex h-12 flex-none items-center justify-end gap-2 border-b border-border bg-surface px-3">
          {/*
            Centred against the content column from `xl` up, by absolute positioning rather than
            by flex order: ordering would make its position depend on the width of the right-hand
            group, so it would visibly drift as the signed-in user's name changes length.
            Below `xl` it returns to normal flow at the left of the bar — a truly centred control
            cannot be both wide and clear of the right-hand group on a narrow laptop (at 1024px
            the free half-width is about 90px), and a flex child cannot overlap its siblings.
          */}
          <span className="mr-auto min-w-0 w-[320px] max-w-[40vw] xl:absolute xl:inset-y-0 xl:left-1/2 xl:mr-0 xl:flex xl:w-[380px] xl:max-w-none xl:-translate-x-1/2 xl:items-center 2xl:w-[420px]">
            <CommandPalette />
          </span>

          <span className="flex items-center gap-2 pl-1">
            <Avatar name={`${user.firstName} ${user.lastName}`} tone="accent" />
            <span className="hidden min-w-0 leading-tight md:block">
              <span className="block truncate text-xs font-semibold">
                {user.firstName} {user.lastName}
              </span>
              <span className="block truncate text-[11px] text-text3">
                {ROLE_LABELS[role] ?? role}
              </span>
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

          <button type="button" onClick={() => logout()} className={TOPBAR_BUTTON}>
            <NavIcon name="signout" className="h-3.5 w-3.5" />
            Sign out
          </button>
        </header>

        <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  )
}
