### Task 9: App shell — left nav, role filtering, theme toggle, property switcher

**Files:**
- Create: `web/src/components/AppShell.tsx` (replacing Task 8's pass-through stub), `web/src/components/NavIcon.tsx`
- Test: `web/src/components/AppShell.test.tsx`

**Interfaces:**
- Consumes: `useSession` (Task 5), `useTheme` (Task 7), `Avatar` / `Badge` / `Dropdown` (Task 4), `useUnreadCount` — **not yet built**, so this task takes the count as an optional prop and Task 16 wires the hook in.
- Produces: `AppShell({ children, unreadCount }: { children: ReactNode; unreadCount?: number })`.

**From the mockups (`Main`, `Board`, `Analytics`, `Admin`):** a 184 px left nav on `--nav`, holding the property tile (`HV` in mono on `--accent`), the property name and a shift/clock line in `--text3`, then 44 px nav rows (`.nav`, active row `bg-surface2` with `text-roomNum`), then a footer with **Theme**, the current user's avatar, their name and role.

Nav items and the capability that shows each — anything else is hidden, not disabled, per §5.2 ("Nav shows only items the role may use"):

| Label | Path | Shown when |
|---|---|---|
| Inbox | `/app/inbox` | `can('reply')` or `can('view_all_conversations')` |
| Board | `/app/board` | `can('create_work_order')` or `can('close_work_order')` |
| Analytics | `/app/analytics` | `can('view_property_analytics')` |
| Alerts | `/app/notifications` | always |
| Admin | `/app/admin/users` | `can('manage_admin')` |

The Inbox and Board rows carry counts in the mockups (`Inbox 23`, `Board 15`). Those come from list queries that later tasks own; this task renders a count only when one is passed, so the shell never fetches.

**Property switcher:** rendered only when `memberships.length > 1`. Switching calls `setPropertyId` and navigates to the role landing for the new membership — the new property's role can differ, and staying on a screen the new role cannot see would immediately bounce.

- [ ] **Step 1: Write the failing test**

`web/src/components/AppShell.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../api/types'
import { SessionProvider } from '../auth/SessionContext'
import { ThemeProvider } from '../theme/ThemeContext'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { AppShell } from './AppShell'

function mount(
  opts: { role?: Role; withSecondProperty?: boolean; secondRole?: Role; unreadCount?: number } = {},
) {
  return renderWithProviders(
    <SessionProvider>
      <ThemeProvider>
        <AppShell unreadCount={opts.unreadCount}>
          <p>screen body</p>
        </AppShell>
      </ThemeProvider>
    </SessionProvider>,
    { session: sessionFixture(opts), route: '/app/inbox' },
  )
}

describe('AppShell', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the screen body and the property identity', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByText('screen body')).toBeInTheDocument()
    expect(screen.getByText('Harbourview Hotel')).toBeInTheDocument()
    expect(screen.getByText('HVH')).toBeInTheDocument()
  })

  it('shows an agent Inbox, Board and Alerts but not Analytics or Admin', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByRole('link', { name: /inbox/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /board/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /alerts/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /analytics/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /admin/i })).not.toBeInTheDocument()
  })

  it('hides the Inbox from corporate, which cannot reply', async () => {
    mount({ role: 'corporate' })
    expect(await screen.findByRole('link', { name: /analytics/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /inbox/i })).not.toBeInTheDocument()
  })

  it('shows Admin only to admin', async () => {
    mount({ role: 'admin' })
    expect(await screen.findByRole('link', { name: /admin/i })).toBeInTheDocument()
  })

  it('marks the current route as the active nav item', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByRole('link', { name: /inbox/i })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: /board/i })).not.toHaveAttribute('aria-current')
  })

  it('shows an unread badge on Alerts only when there is something unread', async () => {
    const { unmount } = mount({ role: 'agent', unreadCount: 3 })
    expect(await screen.findByTestId('unread-badge')).toHaveTextContent('3')
    unmount()
    mount({ role: 'agent', unreadCount: 0 })
    expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument()
  })

  it('names the signed-in user and their role', async () => {
    mount({ role: 'agent' })
    expect(await screen.findByText('Ava')).toBeInTheDocument()
    expect(screen.getByText('Agent')).toBeInTheDocument()
  })

  it('toggles the theme from the nav', async () => {
    mount({ role: 'agent' })
    await userEvent.click(await screen.findByRole('button', { name: /theme/i }))
    await vi.waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
  })

  it('hides the property switcher for a single-property user', async () => {
    mount({ role: 'agent' })
    await screen.findByText('Harbourview Hotel')
    expect(screen.queryByRole('button', { name: /switch property/i })).not.toBeInTheDocument()
  })

  it('offers a property switcher when the user has two memberships', async () => {
    mount({ role: 'agent', withSecondProperty: true })
    await userEvent.click(await screen.findByRole('button', { name: /switch property/i }))
    expect(screen.getByRole('menuitem', { name: /Lakeside Inn/ })).toBeInTheDocument()
  })

  it('switching property stores the choice', async () => {
    mount({ role: 'agent', withSecondProperty: true })
    await userEvent.click(await screen.findByRole('button', { name: /switch property/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Lakeside Inn/ }))
    expect(localStorage.getItem('activePropertyId')).toBe('prop-b')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && npx vitest run src/components/AppShell.test.tsx
```

Expected: FAIL — the pass-through stub renders the body but no nav, so every nav assertion fails.

- [ ] **Step 3: Write `web/src/components/NavIcon.tsx`**

Five inline strokes, matching the mockups' `.ico` (18 px, `stroke: currentColor`, width 1.75, round caps). No icon library.

```tsx
export type IconName = 'inbox' | 'board' | 'analytics' | 'alerts' | 'admin' | 'theme'

const PATHS: Record<IconName, string> = {
  inbox: 'M3 12h5l2 3h4l2-3h5M3 12l2.5-7h13L21 12v7a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-7Z',
  board: 'M4 4h5v16H4zM10 4h5v11h-5zM16 4h4v7h-4z',
  analytics: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  alerts: 'M18 9a6 6 0 1 0-12 0c0 5-2 6-2 6h16s-2-1-2-6M10.5 20a2 2 0 0 0 3 0',
  admin: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7.5 7.5 0 0 0-2-1.2L14.6 3H9.4L9 5.7a7.5 7.5 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7.4 7.4 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7.5 7.5 0 0 0 2 1.2l.4 2.7h5.2l.4-2.7a7.5 7.5 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.06-.4.1-.8.1-1.2Z',
  theme: 'M12 3v2M12 19v2M5 12H3M21 12h-2M6.3 6.3 4.9 4.9M19.1 19.1l-1.4-1.4M6.3 17.7 4.9 19.1M19.1 4.9l-1.4 1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
}

export function NavIcon({ name }: { name: IconName }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-[18px] w-[18px] flex-none"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
```

- [ ] **Step 4: Write `web/src/components/AppShell.tsx`**

```tsx
import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useSession } from '../auth/SessionContext'
import { landingPath, type Capability } from '../auth/capabilities'
import { useTheme } from '../theme/ThemeContext'
import { cn } from '../lib/cn'
import { Avatar, Dropdown } from './ui'
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
            {membership.propertyCode}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-bold">{membership.propertyName}</p>
            <p className="truncate text-[11px] text-text3">{membership.propertyCode}</p>
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
                  <span
                    data-testid="unread-badge"
                    className="rounded bg-danger px-1.5 font-mono text-[11px] font-bold text-avText"
                  >
                    {unreadCount}
                  </span>
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
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 11 shell tests.

- [ ] **Step 6: Verify against the real server**

With the server and `npm run web` running, sign in as each of `ava@hvh.test` (agent), `eli@hvh.test` (dept_staff), `morgan@hvh.test` (manager) and `alex@hvh.test` (admin). Confirm: the nav lists only that role's items, the active row is the amber-text `--surface2` row, **Theme** flips the whole app light and stays light after a reload (that is Task 6's persistence proving itself end to end), and the footer shows the right name and role.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/AppShell.tsx web/src/components/NavIcon.tsx web/src/components/AppShell.test.tsx
git commit -m "feat(web): app shell with role-filtered nav, theme toggle and property switcher"
```

---

