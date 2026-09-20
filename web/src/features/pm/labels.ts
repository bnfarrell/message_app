import type { PmCadence, PmItemType, PmRunStatus, PmUnitKind } from '../../api/types'

export const KINDS: PmUnitKind[] = ['guest_room', 'common_area', 'equipment']

export const KIND_LABELS: Record<PmUnitKind, string> = {
  guest_room: 'Guest Rooms',
  common_area: 'Common & BOH Areas',
  equipment: 'Equipment',
}

export const CADENCE_LABELS: Record<PmCadence, string> = {
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  semiannual: 'Semiannual',
  annual: 'Annual',
}

export const ITEM_TYPE_LABELS: Record<PmItemType, string> = {
  checkbox: 'Checkbox',
  text: 'Text',
  number: 'Number',
  photo: 'Photo',
}

export const RUN_STATUS_LABELS: Record<PmRunStatus, string> = {
  pending: 'Pending',
  in_progress: 'In progress',
  completed: 'Awaiting inspection',
  passed: 'Passed',
  failed: 'Failed',
  missed: 'Missed',
}

export function isKind(value: string | null | undefined): value is PmUnitKind {
  return KINDS.includes(value as PmUnitKind)
}

export { ordinal } from '../../lib/ordinal'

/** "2026-07-01" → "Jul 01". Parsed as calendar parts, so the viewer's timezone can never shift
 *  a property-local cycle boundary onto the previous day. */
export function formatDay(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year!, month! - 1, day!).toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
  })
}

export function formatWindow(startsOn: string, endsOn: string): string {
  return `${formatDay(startsOn)} – ${formatDay(endsOn)}`
}
