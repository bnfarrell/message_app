import type { Priority, WorkOrderStatus } from '../../api/types'

/** Mirrors server/app/domain/work_orders.py TRANSITIONS. Keep the two in step. */
export const TRANSITIONS: Record<WorkOrderStatus, WorkOrderStatus[]> = {
  open: ['assigned', 'in_progress', 'cancelled'],
  assigned: ['in_progress', 'open', 'cancelled'],
  in_progress: ['blocked', 'complete', 'cancelled'],
  blocked: ['in_progress', 'cancelled'],
  complete: ['verified', 'in_progress'],
  verified: [],
  cancelled: [],
}

export const OPEN_STATUSES: WorkOrderStatus[] = [
  'open',
  'assigned',
  'in_progress',
  'blocked',
  'complete',
]

export const BOARD_COLUMNS = OPEN_STATUSES

/** The terminal states. The server leaves them out of a list unless `includeClosed` is set. */
export const CLOSED_STATUSES: WorkOrderStatus[] = ['verified', 'cancelled']

export const STATUS_LABELS: Record<WorkOrderStatus, string> = {
  open: 'Open',
  assigned: 'Assigned',
  in_progress: 'In progress',
  blocked: 'Blocked',
  complete: 'Complete',
  verified: 'Verified',
  cancelled: 'Cancelled',
}

/** Closing a work order needs the close_work_order capability on the server. */
export const CLOSING_STATUSES: WorkOrderStatus[] = ['complete', 'verified', 'cancelled']

export function allowedTransitions(from: WorkOrderStatus): WorkOrderStatus[] {
  return TRANSITIONS[from]
}

export function canTransition(from: WorkOrderStatus, to: WorkOrderStatus): boolean {
  return TRANSITIONS[from].includes(to)
}

export const PRIORITY_TONE: Record<Priority, 'neutral' | 'warn' | 'danger'> = {
  low: 'neutral',
  normal: 'neutral',
  high: 'warn',
  urgent: 'danger',
}
