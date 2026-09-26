import type { MembershipOut, Role } from '../api/types'

export type Capability =
  | 'view_all_conversations'
  | 'reply'
  | 'assign'
  | 'add_note'
  | 'archive'
  | 'create_work_order'
  | 'close_work_order'
  | 'view_property_analytics'
  | 'view_own_stats'
  | 'manage_admin'
  | 'export'
  | 'view_log'
  | 'post_log'
  | 'pin_log_entry'
  | 'view_pm'
  | 'perform_pm'
  | 'inspect_pm'
  | 'view_housekeeping'
  | 'mark_room_dirty'
  | 'perform_housekeeping'
  | 'manage_housekeeping'
  | 'inspect_housekeeping'

const STAFF: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']

/** Mirrors server/app/auth/permissions.py CAPABILITIES. Keep the two in step. */
const CAPABILITIES: Record<Capability, Role[]> = {
  view_all_conversations: ['agent', 'supervisor', 'manager', 'admin', 'corporate'],
  reply: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  assign: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  add_note: STAFF,
  archive: ['agent', 'supervisor', 'manager', 'admin'],
  create_work_order: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  close_work_order: ['dept_staff', 'supervisor', 'manager', 'admin'],
  view_property_analytics: ['supervisor', 'manager', 'admin', 'corporate'],
  view_own_stats: ['agent', 'dept_staff'],
  manage_admin: ['admin', 'corporate'],
  export: ['manager', 'admin', 'corporate'],
  view_log: STAFF,
  post_log: STAFF,
  pin_log_entry: ['supervisor', 'manager', 'admin'],
  view_pm: STAFF,
  perform_pm: ['dept_staff', 'supervisor', 'manager', 'admin'],
  inspect_pm: ['supervisor', 'manager', 'admin'],
  view_housekeeping: STAFF,
  mark_room_dirty: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  perform_housekeeping: ['dept_staff', 'supervisor', 'manager', 'admin'],
  manage_housekeeping: ['supervisor', 'manager', 'admin'],
  inspect_housekeeping: ['supervisor', 'manager', 'admin'],
}

export function hasCapability(role: Role, capability: Capability): boolean {
  return CAPABILITIES[capability].includes(role)
}

/** §5.2: /app redirects here. A housekeeper lands in their room list — docs/design.md calls it
 *  the single decision that does most for adoption — which role alone cannot tell apart from an
 *  engineer, hence the membership. */
export function landingPath(membership: Pick<MembershipOut, 'role' | 'departmentType'>): string {
  switch (membership.role) {
    case 'agent':
      return '/app/inbox'
    case 'dept_staff':
      return membership.departmentType === 'housekeeping' ? '/app/my-rooms' : '/app/board?mine=1'
    case 'supervisor':
      return '/app/board?mine=1'
    case 'manager':
    case 'admin':
    case 'corporate':
      return '/app/analytics'
  }
}
