import type { HkOccupancy, HkServiceType, HkStatus, RoomEventType } from '../../api/types'

export const HK_STATUSES: HkStatus[] = [
  'dirty', 'in_progress', 'clean', 'inspected', 'out_of_order', 'out_of_service',
]

export const HK_STATUS_LABELS: Record<HkStatus, string> = {
  dirty: 'Dirty',
  in_progress: 'In progress',
  clean: 'Awaiting inspection',
  inspected: 'Inspected',
  out_of_order: 'Out of order',
  out_of_service: 'Out of service',
}

/** Tile colours reuse the Badge tones so the board matches the rest of the app. */
export const HK_STATUS_TILE: Record<HkStatus, string> = {
  dirty: 'bg-dangerBg text-dangerText',
  in_progress: 'bg-warnBg text-warnText',
  clean: 'bg-noteBg text-noteText',
  inspected: 'bg-okBg text-okText',
  out_of_order: 'bg-tagBg text-tagText',
  out_of_service: 'bg-tagBg text-tagText',
}

export const SERVICE_LABELS: Record<HkServiceType, string> = {
  departure: 'Departure',
  stayover: 'Stayover',
  touch_up: 'Touch-up',
}

export const OCCUPANCY_LABELS: Record<HkOccupancy, string> = {
  vacant: 'Vacant',
  arrival: 'Arrival',
  stayover: 'Stayover',
  departure: 'Departure',
}

export const OCCUPANCY_GLYPH: Record<HkOccupancy, string> = {
  vacant: '○',
  arrival: '↘',
  stayover: '●',
  departure: '↗',
}

export const EVENT_LABELS: Record<RoomEventType, string> = {
  status_changed: 'Status changed',
  assigned: 'Assigned',
  reassigned: 'Reassigned',
  unassigned: 'Unassigned',
  started: 'Started',
  completed: 'Marked ready',
  inspection_passed: 'Passed inspection',
  inspection_failed: 'Failed inspection',
  marked_dirty: 'Marked dirty',
  rush_set: 'Rush set',
  rush_cleared: 'Rush cleared',
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0]!.toUpperCase())
    .slice(0, 2)
    .join('')
}
