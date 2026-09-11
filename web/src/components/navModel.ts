import type { Capability } from '../auth/capabilities'
import type { IconName } from './NavIcon'

export type NavItem = { label: string; to: string; icon: IconName; needs: Capability[] }
export type NavGroup = { heading: string; items: NavItem[] }

// `needs` is an OR: any one capability is enough to see the item. An empty `needs` is
// always visible. A group whose items are all filtered out renders nothing at all —
// not an empty heading.
export const NAV_GROUPS: NavGroup[] = [
  {
    heading: 'Overview',
    items: [
      // Corporate has view_all_conversations + add_note on the server (permissions.py) with no
      // @require_capability gate on the list endpoint, so it genuinely can read (and note) every
      // conversation — the Inbox stays visible, read-only.
      { label: 'Inbox', to: '/app/inbox', icon: 'inbox', needs: ['reply', 'view_all_conversations'] },
      { label: 'Board', to: '/app/board', icon: 'board', needs: ['create_work_order', 'close_work_order'] },
      { label: 'Alerts', to: '/app/notifications', icon: 'alerts', needs: [] },
    ],
  },
  {
    heading: 'Insights',
    items: [
      { label: 'Analytics', to: '/app/analytics', icon: 'analytics', needs: ['view_property_analytics'] },
    ],
  },
  {
    // Ruling D62: one entry, not the six admin screens. Admin.dc.html carries its own 220px
    // sub-nav, including the three greyed Phase 2 items; hoisting the screens here would either
    // duplicate that navigation or force permanently-disabled entries into the global rail.
    heading: 'Admin',
    items: [{ label: 'Admin', to: '/app/admin/users', icon: 'admin', needs: ['manage_admin'] }],
  },
]

// Absolute targets: AdminPage is mounted at the "admin/*" splat, and this project's router
// future flags (v7_relativeSplatPath) resolve a plain relative `to` against the full current
// splat path rather than the section's own directory, so a relative "users" link from
// "/app/admin/quick-replies" resolves to ".../quick-replies/users" instead of ".../users".
export const ADMIN_SECTIONS = [
  { to: '/app/admin/users', label: 'Users & roles' },
  { to: '/app/admin/departments', label: 'Departments' },
  { to: '/app/admin/quick-replies', label: 'Quick replies' },
  { to: '/app/admin/assets', label: 'Digital assets' },
  { to: '/app/admin/categories', label: 'Resolution categories' },
  { to: '/app/admin/property', label: 'Property settings' },
]

/** The rail and the command palette must never disagree about what a role can reach. */
export function visibleNavGroups(can: (capability: Capability) => boolean): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.needs.length === 0 || item.needs.some(can)),
  })).filter((group) => group.items.length > 0)
}
