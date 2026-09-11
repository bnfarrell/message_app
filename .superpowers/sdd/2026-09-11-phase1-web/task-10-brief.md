### Task 10: SMS segments, time formatting and the SLA chip

**Files:**
- Create: `web/src/lib/segments.ts`, `web/src/lib/time.ts`, `web/src/components/SlaChip.tsx`
- Test: `web/src/lib/segments.test.ts`, `web/src/lib/time.test.ts`, `web/src/components/SlaChip.test.tsx`

**Interfaces:**
- Consumes: `cn` (Task 1), `Badge` (Task 4).
- Produces:
  - `isGsm7(body: string): boolean`, `segmentCount(body: string): number`, `charCount(body: string): number`
  - `formatCountdown(ms: number): string` → `mm:ss`, or `−mm:ss` (U+2212) when negative; hours roll into minutes (`92:07`)
  - `relativeTime(iso: string, now?: Date): string` → `now`, `4m`, `1h 10m`, `2d`
  - `formatClock(iso: string): string` → `18:58` in the browser's locale, 24-hour
  - `formatDuration(seconds: number): string` → `38m`, `1h 14m`, `2m 40s` (used by analytics and the WO timeline)
  - `slaState(args: { dueAt: string | null; startAt: string | null; answered: boolean; now: Date }): { tone: 'ok' | 'warn' | 'danger' | 'done'; label: string } | null`
  - `SlaChip({ dueAt, startAt, answered }: { dueAt?: string | null; startAt?: string | null; answered?: boolean })`

**`segments.ts` mirrors `server/app/domain/sms.py` exactly.** The rule (GSM 03.38): GSM-7 text is 160 septets in one segment, then 153 per segment; non-GSM-7 is UCS-2, 70 UTF-16 code units in one segment, then 67 per segment. Characters in the GSM-7 *extension* table cost **two** septets. `charCount` is `[...body].length` — user-visible characters, so an emoji counts once even though it costs two UTF-16 units.

**The mockup's exact SLA treatment** (`docs/mockups/Main.dc.html`, `.timer`): `--dangerBg`/`--dangerText` with a leading U+2212 when overdue (`−04:12`), `--warnBg`/`--warnText` past two thirds (`03:05`), `--okBg`/`--okText` otherwise (`11:40`), and `--timerDoneBg`/`--timerDoneText` reading `done` once answered. §5.3 fixes the amber threshold at 66 % elapsed. The window is `startAt → dueAt` where `startAt` is the conversation's `lastGuestMessageAt`; with `sla_minutes=15` the mockup's `03:05` remaining is 79 % elapsed (amber) and `11:40` remaining is 22 % (green), which is the arithmetic these tests pin.

- [ ] **Step 1: Write the failing segment and time tests**

`web/src/lib/segments.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { charCount, isGsm7, segmentCount } from './segments'

describe('isGsm7', () => {
  it('accepts plain ASCII and the GSM basic extras', () => {
    expect(isGsm7('Checkout is 11 AM.')).toBe(true)
    expect(isGsm7('£¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ')).toBe(true)
  })

  it('accepts the extension characters', () => {
    expect(isGsm7('^{}\\[~]|€')).toBe(true)
  })

  it('rejects a curly quote, an em dash and an emoji', () => {
    expect(isGsm7('don’t')).toBe(false)
    expect(isGsm7('a — b')).toBe(false)
    expect(isGsm7('thanks \u{1F600}')).toBe(false)
  })
})

describe('segmentCount', () => {
  it('is 0 for an empty body', () => {
    expect(segmentCount('')).toBe(0)
  })

  it('holds 160 GSM-7 septets in one segment', () => {
    expect(segmentCount('a'.repeat(160))).toBe(1)
  })

  it('splits at 161 into two', () => {
    expect(segmentCount('a'.repeat(161))).toBe(2)
  })

  it('fits 306 septets in two segments and 307 in three', () => {
    expect(segmentCount('a'.repeat(306))).toBe(2)
    expect(segmentCount('a'.repeat(307))).toBe(3)
  })

  it('counts an extension character as two septets', () => {
    // 159 plain + one 2-septet '€' = 161 septets, so it spills to a second segment.
    expect(segmentCount('a'.repeat(159) + '€')).toBe(2)
    expect(segmentCount('a'.repeat(158) + '€')).toBe(1)
  })

  it('holds 70 UCS-2 code units in one segment', () => {
    expect(segmentCount('日'.repeat(70))).toBe(1)
    expect(segmentCount('日'.repeat(71))).toBe(2)
  })

  it('counts a surrogate pair as two UCS-2 units, matching the server', () => {
    // 35 emoji = 70 UTF-16 units = 1 segment; 36 = 72 units = 2.
    expect(segmentCount('\u{1F600}'.repeat(35))).toBe(1)
    expect(segmentCount('\u{1F600}'.repeat(36))).toBe(2)
  })

  it('fits 134 UCS-2 units in two segments and 135 in three', () => {
    expect(segmentCount('日'.repeat(134))).toBe(2)
    expect(segmentCount('日'.repeat(135))).toBe(3)
  })
})

describe('charCount', () => {
  it('counts user-visible characters, not UTF-16 units', () => {
    expect(charCount('abc')).toBe(3)
    expect(charCount('\u{1F600}')).toBe(1)
  })
})
```

`web/src/lib/time.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatCountdown, formatDuration, relativeTime } from './time'

describe('formatCountdown', () => {
  it('formats remaining time as mm:ss', () => {
    expect(formatCountdown(4 * 60_000 + 12_000)).toBe('04:12')
    expect(formatCountdown(11 * 60_000 + 40_000)).toBe('11:40')
  })

  it('uses a real minus sign when overdue, matching the mockup', () => {
    expect(formatCountdown(-(4 * 60_000 + 12_000))).toBe('−' + '04:12')
  })

  it('rolls hours into minutes rather than showing h:mm:ss', () => {
    expect(formatCountdown(92 * 60_000 + 7_000)).toBe('92:07')
  })

  it('shows 00:00 at exactly zero', () => {
    expect(formatCountdown(0)).toBe('00:00')
  })
})

describe('relativeTime', () => {
  const now = new Date('2026-09-10T19:00:00Z')

  it('says now for the last minute', () => {
    expect(relativeTime('2026-09-10T18:59:30Z', now)).toBe('now')
  })

  it('counts whole minutes under an hour', () => {
    expect(relativeTime('2026-09-10T18:56:00Z', now)).toBe('4m')
    expect(relativeTime('2026-09-10T18:22:00Z', now)).toBe('38m')
  })

  it('shows hours and minutes under a day', () => {
    expect(relativeTime('2026-09-10T17:50:00Z', now)).toBe('1h 10m')
    expect(relativeTime('2026-09-10T17:00:00Z', now)).toBe('2h')
  })

  it('shows whole days beyond that', () => {
    expect(relativeTime('2026-09-08T19:00:00Z', now)).toBe('2d')
  })
})

describe('formatDuration', () => {
  it('formats sub-minute values with seconds', () => {
    expect(formatDuration(160)).toBe('2m 40s')
    expect(formatDuration(45)).toBe('45s')
  })

  it('drops seconds once past an hour', () => {
    expect(formatDuration(4440)).toBe('1h 14m')
  })

  it('formats whole minutes without seconds', () => {
    expect(formatDuration(2280)).toBe('38m')
  })
})
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd web && npx vitest run src/lib
```

Expected: FAIL — neither module resolves.

- [ ] **Step 3: Write `web/src/lib/segments.ts`**

```ts
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
```

- [ ] **Step 4: Write `web/src/lib/time.ts`**

```ts
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
```

- [ ] **Step 5: Write the failing SLA chip test**

`web/src/components/SlaChip.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SlaChip, slaState } from './SlaChip'

// A 15-minute window, as seeded (property settings sla_minutes = 15).
const START = '2026-09-10T18:41:00Z'
const DUE = '2026-09-10T18:56:00Z'

function at(iso: string) {
  return new Date(iso)
}

describe('slaState', () => {
  it('is done once the conversation has been answered', () => {
    expect(slaState({ dueAt: DUE, startAt: START, answered: true, now: at(START) })).toEqual({
      tone: 'done',
      label: 'done',
    })
  })

  it('is null with no due date, so no chip is rendered', () => {
    expect(slaState({ dueAt: null, startAt: START, answered: false, now: at(START) })).toBeNull()
  })

  it('is green early in the window', () => {
    // 3:20 elapsed of 15:00 = 22%; 11:40 remaining — the mockup's green row.
    const state = slaState({
      dueAt: DUE,
      startAt: START,
      answered: false,
      now: at('2026-09-10T18:44:20Z'),
    })
    expect(state).toEqual({ tone: 'ok', label: '11:40' })
  })

  it('turns amber at exactly two thirds elapsed', () => {
    // The window is 15:00 = 900s, so two thirds is 600s elapsed → 18:51:00Z.
    // (Not 594s: 66.0% is below 2/3 and must still be green.)
    const state = slaState({
      dueAt: DUE,
      startAt: START,
      answered: false,
      now: at('2026-09-10T18:51:00Z'),
    })
    expect(state?.tone).toBe('warn')
  })

  it('is still green one second before two thirds', () => {
    const state = slaState({
      dueAt: DUE,
      startAt: START,
      answered: false,
      now: at('2026-09-10T18:50:59Z'),
    })
    expect(state?.tone).toBe('ok')
  })

  it('matches the mockup amber row', () => {
    // 11:55 elapsed, 3:05 remaining
    const state = slaState({
      dueAt: DUE,
      startAt: START,
      answered: false,
      now: at('2026-09-10T18:52:55Z'),
    })
    expect(state).toEqual({ tone: 'warn', label: '03:05' })
  })

  it('turns red past due with a minus-signed countdown', () => {
    const state = slaState({
      dueAt: DUE,
      startAt: START,
      answered: false,
      now: at('2026-09-10T19:00:12Z'),
    })
    expect(state).toEqual({ tone: 'danger', label: '−04:12' })
  })

  it('is red at exactly the due moment, not amber', () => {
    expect(slaState({ dueAt: DUE, startAt: START, answered: false, now: at(DUE) })?.tone).toBe(
      'danger',
    )
  })

  it('falls back to amber-vs-green on remaining time when the start is unknown', () => {
    // No startAt means no window to measure; anything still in the future is green.
    const state = slaState({
      dueAt: DUE,
      startAt: null,
      answered: false,
      now: at('2026-09-10T18:44:20Z'),
    })
    expect(state).toEqual({ tone: 'ok', label: '11:40' })
  })
})

describe('SlaChip', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(at('2026-09-10T18:52:55Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the countdown in mono with the warn tokens', () => {
    render(<SlaChip dueAt={DUE} startAt={START} />)
    const chip = screen.getByText('03:05')
    expect(chip.className).toContain('font-mono')
    expect(chip.className).toContain('bg-warnBg')
  })

  it('renders done with the muted timer tokens', () => {
    render(<SlaChip dueAt={DUE} startAt={START} answered />)
    expect(screen.getByText('done').className).toContain('bg-timerDoneBg')
  })

  it('renders nothing without a due date', () => {
    const { container } = render(<SlaChip dueAt={null} startAt={START} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('ticks without a reload', () => {
    render(<SlaChip dueAt={DUE} startAt={START} />)
    expect(screen.getByText('03:05')).toBeInTheDocument()
    vi.advanceTimersByTime(5000)
    expect(screen.getByText('03:00')).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Run it to verify it fails**

```bash
cd web && npx vitest run src/components/SlaChip.test.tsx
```

Expected: FAIL — cannot resolve `./SlaChip`.

- [ ] **Step 7: Write `web/src/components/SlaChip.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { cn } from '../lib/cn'
import { formatCountdown } from '../lib/time'

const AMBER_AT = 2 / 3 // §5.3: amber at 66% of the window elapsed

type Tone = 'ok' | 'warn' | 'danger' | 'done'

const TONES: Record<Tone, string> = {
  ok: 'bg-okBg text-okText',
  warn: 'bg-warnBg text-warnText',
  danger: 'bg-dangerBg text-dangerText',
  done: 'bg-timerDoneBg text-timerDoneText',
}

export function slaState(args: {
  dueAt: string | null
  startAt: string | null
  answered: boolean
  now: Date
}): { tone: Tone; label: string } | null {
  const { dueAt, startAt, answered, now } = args
  if (answered) return { tone: 'done', label: 'done' }
  if (!dueAt) return null

  const due = new Date(dueAt).getTime()
  const remaining = due - now.getTime()
  if (remaining <= 0) return { tone: 'danger', label: formatCountdown(remaining) }

  const label = formatCountdown(remaining)
  if (!startAt) return { tone: 'ok', label }

  const start = new Date(startAt).getTime()
  const window = due - start
  // A non-positive window carries no information; treat it as still in hand.
  if (window <= 0) return { tone: 'ok', label }
  const elapsed = (now.getTime() - start) / window
  return { tone: elapsed >= AMBER_AT ? 'warn' : 'ok', label }
}

export function SlaChip({
  dueAt,
  startAt,
  answered = false,
  className,
}: {
  dueAt?: string | null
  startAt?: string | null
  answered?: boolean
  className?: string
}) {
  // One second is the smallest unit the chip shows, so that is the tick.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    if (answered || !dueAt) return
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [answered, dueAt])

  const state = slaState({ dueAt: dueAt ?? null, startAt: startAt ?? null, answered, now })
  if (!state) return null

  return (
    <span
      className={cn(
        'inline-flex h-7 min-w-[64px] items-center justify-center rounded-md px-2.5',
        'font-mono text-[13px] font-semibold',
        TONES[state.tone],
        className,
      )}
    >
      {state.label}
    </span>
  )
}
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 13 segment tests, 11 time tests, 13 SLA tests.

- [ ] **Step 9: Cross-check the segment counter against the server**

The two implementations must agree or the composer lies about cost. Confirm on the boundaries the server's own tests use:

```bash
cd server && python -c "from app.domain.sms import segment_count as s; print([s('a'*160), s('a'*161), s('a'*306), s('a'*307), s('a'*159+'€'), s('日'*70), s('日'*71), s('\U0001F600'*35), s('\U0001F600'*36)])"
```

Expected: `[1, 2, 2, 3, 2, 1, 2, 1, 2]` — identical to the TypeScript assertions above. If any pair disagrees, **report it as a defect rather than changing the TypeScript to match**: the server is the side that bills, and a genuine mismatch needs a decision, not a silent alignment.

- [ ] **Step 10: Commit**

```bash
git add web/src/lib/segments.ts web/src/lib/time.ts web/src/components/SlaChip.tsx \
        web/src/lib/segments.test.ts web/src/lib/time.test.ts web/src/components/SlaChip.test.tsx
git commit -m "feat(web): SMS segment counter mirroring the server, time helpers and the SLA chip"
```

---

