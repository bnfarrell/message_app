import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { cn } from '../../lib/cn'
import { AssetsAdmin } from './AssetsAdmin'
import { CategoriesAdmin } from './CategoriesAdmin'
import { QuickRepliesAdmin } from './QuickRepliesAdmin'
import { UsersAdmin } from './UsersAdmin'

// Absolute targets: AdminPage is mounted at the "admin/*" splat, and this project's router
// future flags (v7_relativeSplatPath) resolve a plain relative `to` against the full current
// splat path rather than the section's own directory, so a relative "users" link from
// "/app/admin/quick-replies" resolves to ".../quick-replies/users" instead of ".../users".
const LIVE = [
  { to: '/app/admin/users', label: 'Users & roles' },
  { to: '/app/admin/quick-replies', label: 'Quick replies' },
  { to: '/app/admin/assets', label: 'Digital assets' },
  { to: '/app/admin/categories', label: 'Resolution categories' },
]

// Shown deliberately (mockup Admin.dc.html): an admin should see the product's shape.
const PHASE_2 = ['Departments', 'Property settings', 'Automations', 'Blocked numbers', 'Integrations']

export function AdminPage() {
  return (
    <div className="flex h-full">
      <nav className="w-[220px] flex-none border-r border-border p-3">
        <h1 className="mb-3 px-2 text-base font-bold">Admin</h1>
        <ul className="flex flex-col gap-0.5">
          {LIVE.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex h-10 items-center rounded px-3 text-sm font-semibold',
                    isActive
                      ? 'bg-surface2 text-text shadow-[inset_3px_0_0_var(--accent)]'
                      : 'text-text3 hover:text-text',
                  )
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
          {PHASE_2.map((label) => (
            <li
              key={label}
              aria-disabled="true"
              className="flex h-10 cursor-not-allowed items-center rounded px-3 text-sm font-semibold text-text4"
            >
              {label}
            </li>
          ))}
        </ul>
        <p className="mt-3 px-3 text-xs text-text4">Greyed items arrive in Phase 2</p>
      </nav>

      <Routes>
        <Route index element={<Navigate to="users" replace />} />
        <Route path="users" element={<UsersAdmin />} />
        <Route path="quick-replies" element={<QuickRepliesAdmin />} />
        <Route path="assets" element={<AssetsAdmin />} />
        <Route path="categories" element={<CategoriesAdmin />} />
      </Routes>
    </div>
  )
}
