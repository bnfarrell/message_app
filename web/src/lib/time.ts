const MINUS = '−' // U+2212, the mockup's minus — not a hyphen

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** mm:ss, with minutes allowed past 59 so a long overdue timer stays readable. */
export function formatCountdown(ms: number): string {
  const overdue = ms < 0
  const total = Math.floor(Math.abs(ms) / 1000)
  const body = `${pad(Math.floor(total / 60))}:${pad(total % 60)}`
  return overdue ? MINUS + body : body
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    const rest = minutes % 60
    return rest ? `${hours}h ${rest}m` : `${hours}h`
  }
  return `${Math.floor(hours / 24)}d`
}

/** The viewer's local calendar day, as `YYYY-MM-DD` — for grouping the log feed only.
 *  Every clock in this app already renders in the viewer's zone (see `formatClock`
 *  below), and the property timezone is not plumbed into any display component, so this
 *  reads local Date fields rather than the property's. */
export function dayKey(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    const rest = Math.round(seconds % 60)
    return rest ? `${minutes}m ${rest}s` : `${minutes}m`
  }
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}
