/**
 * English ordinal: 1st, 2nd, 3rd, 4th. The 11/12/13 exception is the whole point — they
 * take "th" despite ending in 1/2/3 — but so is the plain `${n}th` this replaces, which
 * rendered a second-time guest as "2th stay".
 */
export function ordinal(n: number): string {
  const tens = Math.abs(n) % 100
  if (tens >= 11 && tens <= 13) return `${n}th`
  switch (Math.abs(n) % 10) {
    case 1:
      return `${n}st`
    case 2:
      return `${n}nd`
    case 3:
      return `${n}rd`
    default:
      return `${n}th`
  }
}
