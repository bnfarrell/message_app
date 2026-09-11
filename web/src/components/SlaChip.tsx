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
