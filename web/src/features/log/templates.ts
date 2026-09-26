import type { LogFieldType, LogFieldValueOut, LogTemplateOut } from '../../api/types'

export const FIELD_TYPE_LABELS: Record<LogFieldType, string> = {
  short_text: 'Short text',
  long_text: 'Long text',
  integer: 'Whole number',
  decimal: 'Number',
  percent: 'Percent',
}

export const NUMERIC_FIELD_TYPES: ReadonlySet<LogFieldType> = new Set(['integer', 'decimal', 'percent'])

/** Mirrors the server's `log_templates.format_value`: at most two decimals, trailing zeros
 *  dropped, and a percent as `87%`. */
export function formatFieldValue(value: LogFieldValueOut): string {
  if (value.numberValue === null || value.numberValue === undefined) return value.textValue ?? ''
  const shown = String(Number(value.numberValue.toFixed(2)))
  return value.fieldType === 'percent' ? `${shown}%` : shown
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** "Everyone" for an empty audience, else e.g. "3 users, 1 department" (spec §4.3). */
export function audienceSummary(audience: LogTemplateOut['audience']): string {
  const users = audience.filter((ref) => ref.type === 'user').length
  const departments = audience.length - users
  const parts = [
    ...(users ? [plural(users, 'user')] : []),
    ...(departments ? [plural(departments, 'department')] : []),
  ]
  return parts.length ? parts.join(', ') : 'Everyone'
}
