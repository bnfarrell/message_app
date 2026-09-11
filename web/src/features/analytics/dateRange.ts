export type RangeKey = 'today' | '7d' | '30d'

function iso(date: Date): string {
  // Local date parts, not UTC: "today" must mean the operator's today.
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** The server treats a bare date `to` as end-of-day, so these ranges are inclusive. */
export function rangeFor(key: RangeKey, now: Date = new Date()): { from: string; to: string } {
  const to = iso(now)
  if (key === 'today') return { from: to, to }
  const days = key === '7d' ? 6 : 29
  const start = new Date(now)
  start.setDate(start.getDate() - days)
  return { from: iso(start), to }
}

export const RANGE_LABELS: Record<RangeKey, string> = {
  today: 'Today',
  '7d': '7 days',
  '30d': '30 days',
}
