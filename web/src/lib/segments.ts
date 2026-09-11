/**
 * Mirrors server/app/domain/sms.py. GSM 03.38: 160/153 septets for GSM-7,
 * 70/67 UTF-16 code units for UCS-2. Keep the two in step — the composer's
 * count is a promise about what the carrier will charge for.
 */
const GSM7_BASIC = new Set(
  '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà',
)
const GSM7_EXTENDED = new Set('^{}\\[~]|€\f')

export function isGsm7(body: string): boolean {
  for (const ch of body) if (!GSM7_BASIC.has(ch) && !GSM7_EXTENDED.has(ch)) return false
  return true
}

function gsm7Septets(body: string): number {
  let total = 0
  for (const ch of body) total += GSM7_EXTENDED.has(ch) ? 2 : 1
  return total
}

/** UTF-16 code units, which is what a UCS-2 SMS counts. */
function utf16Units(body: string): number {
  return body.length
}

export function segmentCount(body: string): number {
  if (!body) return 0
  if (isGsm7(body)) {
    const n = gsm7Septets(body)
    return n <= 160 ? 1 : Math.ceil(n / 153)
  }
  const n = utf16Units(body)
  return n <= 70 ? 1 : Math.ceil(n / 67)
}

/** User-visible characters: one emoji is one character even though it is two code units. */
export function charCount(body: string): number {
  return [...body].length
}
