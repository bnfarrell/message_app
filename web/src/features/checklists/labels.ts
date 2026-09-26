import type { ChecklistKind, ChecklistSchedule, ChecklistStatus, Shift } from '../../api/types'

export const SHIFT_LABELS: Record<Shift, string> = {
  am: 'AM',
  pm: 'PM',
  overnight: 'Overnight',
}

export const STATUS_LABELS: Record<ChecklistStatus, string> = {
  open: 'Open',
  in_progress: 'In progress',
  complete: 'Complete',
  missed: 'Missed',
}

export const STATUS_TONE: Record<ChecklistStatus, 'neutral' | 'note' | 'ok' | 'danger'> = {
  open: 'neutral',
  in_progress: 'note',
  complete: 'ok',
  missed: 'danger',
}

export const KIND_LABELS: Record<ChecklistKind, string> = {
  normal: 'Normal',
  readings: 'Readings',
}

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function weekdayLabel(mask: number | null | undefined): string {
  if (!mask) return '—'
  if (mask === 127) return 'Every day'
  return WEEKDAYS.filter((_, i) => (mask >> i) & 1).join(', ')
}

/** How a template's schedule reads in a list. An unscheduled one is a call to action
 *  (checklist structure spec §4.1). */
export function scheduleLabel(t: {
  schedule: ChecklistSchedule
  shift?: Shift | null
  weekdays?: number | null
}): string {
  if (t.schedule === 'on_demand') return 'On demand'
  if (t.schedule === 'unscheduled') return 'Set schedule'
  return `${t.shift ? SHIFT_LABELS[t.shift] : ''} · ${weekdayLabel(t.weekdays)}`
}
