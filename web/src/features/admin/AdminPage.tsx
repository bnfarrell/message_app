import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { cn } from '../../lib/cn'
import { ADMIN_SECTIONS } from '../../components/navModel'
import { AssetsAdmin } from './AssetsAdmin'
import { CategoriesAdmin } from './CategoriesAdmin'
import { DepartmentsAdmin } from './DepartmentsAdmin'
import { PropertySettingsAdmin } from './PropertySettingsAdmin'
import { QuickRepliesAdmin } from './QuickRepliesAdmin'
import { UnitsAdmin } from './UnitsAdmin'
import { UsersAdmin } from './UsersAdmin'

// Shared with the Ctrl+K palette so the two can never disagree about what Admin contains;
// the reason the targets are absolute is recorded beside the list.

// Shown deliberately (mockup Admin.dc.html): an admin should see the product's shape.
const PHASE_2 = ['Automations', 'Blocked numbers', 'Integrations']

export function AdminPage() {
  return (
    <div className="flex h-full">
      <nav className="w-[220px] flex-none border-r border-border p-3">
        <h1 className="mb-3 px-2 text-base font-bold">Admin</h1>
        <ul className="flex flex-col gap-0.5">
          {ADMIN_SECTIONS.map((item) => (
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
        <Route path="departments" element={<DepartmentsAdmin />} />
        <Route path="quick-replies" element={<QuickRepliesAdmin />} />
        <Route path="assets" element={<AssetsAdmin />} />
        <Route path="categories" element={<CategoriesAdmin />} />
        <Route path="property" element={<PropertySettingsAdmin />} />
        <Route path="units" element={<UnitsAdmin />} />
      </Routes>
    </div>
  )
}
