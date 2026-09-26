import type { Capability } from '../auth/capabilities'
import type { IconName } from './NavIcon'

export type NavItem = {
  label: string
  to: string
  icon: IconName
  needs: Capability[]
  /** Path prefixes that count as "inside this section", when they are not just `to`.
   *
   * A rail entry needs one path to navigate to and a possibly broader one to light up for.
   * React Router's own `isActive` only knows `to`, so it lights an entry on `to` and its
   * descendants — and an entry that points at one screen of a section (Admin lands on Users &
   * roles) went dark on every sibling screen of that same section, which is what a user
   * reported for Admin on Departments. */
  match?: string[]
}
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
      // A work order opens at /app/work-orders/:id, a sibling of the board rather than a child
      // of it — the same shape as the Admin defect, so it is listed here too.
      { label: 'Board', to: '/app/board', icon: 'board', needs: ['create_work_order', 'close_work_order'], match: ['/app/board', '/app/work-orders'] },
      { label: 'Alerts', to: '/app/notifications', icon: 'alerts', needs: [] },
      { label: 'Messages', to: '/app/messages', icon: 'inbox', needs: [] },
      { label: 'Log', to: '/app/log', icon: 'log', needs: [] },
      { label: 'Checklists', to: '/app/checklists', icon: 'checklist', needs: ['view_checklists'], match: ['/app/checklists'] },
    ],
  },
  {
    heading: 'Housekeeping',
    items: [
      { label: 'Rooms', to: '/app/housekeeping', icon: 'bed', needs: ['view_housekeeping'] },
      { label: 'My Rooms', to: '/app/my-rooms', icon: 'log', needs: ['perform_housekeeping'] },
      // A sibling of /app/housekeeping rather than a child, so Rooms does not light with it —
      // the same reason PM Inspection is /app/inspection: two lit entries reads as a bug.
      {
        label: 'Room Inspection',
        to: '/app/room-inspection',
        icon: 'inspect',
        needs: ['inspect_housekeeping'],
      },
    ],
  },
  {
    heading: 'Maintenance',
    items: [
      // Runs and the compliance tab live under /app/pm, so the prefix lights for all of them.
      // The inspection queue is a sibling at /app/inspection precisely so it does not: two lit
      // entries reads as a bug.
      {
        label: 'Preventative Maintenance',
        to: '/app/pm',
        icon: 'wrench',
        needs: ['view_pm'],
        match: ['/app/pm'],
      },
      { label: 'PM Inspection', to: '/app/inspection', icon: 'inspect', needs: ['inspect_pm'] },
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
    items: [
      {
        label: 'Admin',
        to: '/app/admin/users',
        icon: 'admin',
        needs: ['manage_admin'],
        match: ['/app/admin'],
      },
    ],
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
  { to: '/app/admin/units', label: 'Maintainable units' },
  { to: '/app/admin/pm-templates', label: 'PM templates' },
  { to: '/app/admin/checklist-templates', label: 'Checklist templates' },
]

/** Whether `pathname` is inside this item's section. Compared by whole path segments, so
 *  /app/administration can never light the /app/admin entry. */
export function isNavItemActive(item: NavItem, pathname: string): boolean {
  return (item.match ?? [item.to]).some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
}

/** The rail and the command palette must never disagree about what a role can reach. */
export function visibleNavGroups(can: (capability: Capability) => boolean): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.needs.length === 0 || item.needs.some(can)),
  })).filter((group) => group.items.length > 0)
}
