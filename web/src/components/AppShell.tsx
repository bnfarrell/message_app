import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useSession } from '../auth/SessionContext'
import { landingPath, type Capability } from '../auth/capabilities'
import { useTheme } from '../theme/ThemeContext'
import { cn } from '../lib/cn'
import { Avatar, Badge, Dropdown } from './ui'
import { NavIcon, type IconName } from './NavIcon'

const ROLE_LABELS: Record<string, string> = {
  agent: 'Agent',
  dept_staff: 'Staff',
  supervisor: 'Supervisor',
  manager: 'Duty manager',
  admin: 'Admin',
  corporate: 'Corporate',
}

type NavItem = { label: string; to: string; icon: IconName; needs: Capability[] }

// `needs` is an OR: any one capability is enough to see the item.
const NAV: NavItem[] = [
  // Corporate has view_all_conversations + add_note on the server (permissions.py) with no
  // @require_capability gate on the list endpoint, so it genuinely can read (and note) every
  // conversation — the Inbox stays visible, read-only until Task 14 hides the composer.
  { label: 'Inbox', to: '/app/inbox', icon: 'inbox', needs: ['reply', 'view_all_conversations'] },
  { label: 'Board', to: '/app/board', icon: 'board', needs: ['create_work_order', 'close_work_order'] },
  { label: 'Analytics', to: '/app/analytics', icon: 'analytics', needs: ['view_property_analytics'] },
  { label: 'Alerts', to: '/app/notifications', icon: 'alerts', needs: [] },
  { label: 'Admin', to: '/app/admin/users', icon: 'admin', needs: ['manage_admin'] },
]

export function AppShell({
  children,
  unreadCount,
}: {
  children: ReactNode
  unreadCount?: number
}) {
  const { user, membership, memberships, role, can, setPropertyId } = useSession()
  const { resolved, setTheme } = useTheme()
  const navigate = useNavigate()

  const visible = NAV.filter((item) => item.needs.length === 0 || item.needs.some(can))

  return (
    <div className="flex h-full bg-bg">
      <nav className="flex w-[184px] flex-none flex-col border-r border-border bg-nav p-3">
        <div className="mb-5 flex items-center gap-2.5 px-1">
          <span className="grid h-8 w-8 flex-none place-items-center rounded-md bg-accent font-mono text-xs font-bold text-accentText">
            {membership.propertyCode.slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-bold">{membership.propertyName}</p>
            <p className="truncate font-mono text-[11px] text-text3">{membership.propertyCode}</p>
          </div>
        </div>

        <ul className="flex flex-col gap-1">
          {visible.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex h-11 items-center gap-3 rounded px-3.5 text-sm font-semibold',
                    isActive ? 'bg-surface2 text-roomNum' : 'text-text3 hover:text-text',
                  )
                }
              >
                <NavIcon name={item.icon} />
                <span className="flex-1">{item.label}</span>
                {item.label === 'Alerts' && unreadCount ? (
                  <Badge tone="danger" className="font-mono">
                    <span data-testid="unread-badge">{unreadCount}</span>
                  </Badge>
                ) : null}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="mt-auto flex flex-col gap-2 border-t border-border pt-3">
          {memberships.length > 1 ? (
            <Dropdown label={<span className="text-xs">Switch property</span>}>
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
          ) : null}

          <button
            type="button"
            onClick={() => setTheme(resolved === 'dark' ? 'light' : 'dark')}
            className="flex h-11 items-center gap-3 rounded px-3.5 text-sm font-semibold text-text3 hover:text-text"
          >
            <NavIcon name="theme" />
            Theme
          </button>

          <div className="flex items-center gap-2.5 px-1 py-2">
            <Avatar name={`${user.firstName} ${user.lastName}`} tone="accent" />
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold">{user.firstName}</p>
              <p className="truncate text-[11px] text-text3">{ROLE_LABELS[role] ?? role}</p>
            </div>
          </div>
        </div>
      </nav>

      <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
