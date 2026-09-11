import type { Role } from '../api/types'

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
}

export function hasCapability(role: Role, capability: Capability): boolean {
  return CAPABILITIES[capability].includes(role)
}

/** §5.2: /app redirects here. */
export function landingPath(role: Role): string {
  switch (role) {
    case 'agent':
      return '/app/inbox'
    case 'dept_staff':
    case 'supervisor':
      return '/app/board?mine=1'
    case 'manager':
    case 'admin':
    case 'corporate':
      return '/app/analytics'
  }
}
