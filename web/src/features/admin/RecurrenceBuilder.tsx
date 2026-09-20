import { useEffect, useRef, useState } from 'react'
import { Button, Input } from '../../components/ui'

export type SimpleFreq = 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY'
const FREQS: { value: SimpleFreq; label: string }[] = [
  { value: 'DAILY', label: 'days' },
  { value: 'WEEKLY', label: 'weeks' },
  { value: 'MONTHLY', label: 'months' },
  { value: 'YEARLY', label: 'years' },
]
const SIMPLE = /^FREQ=(DAILY|WEEKLY|MONTHLY|YEARLY)(?:;INTERVAL=(\d+))?$/

/** The subset the controls can express: FREQ plus an optional INTERVAL, nothing else.
 *  An empty rule reads as "every 1 month" so a new template starts somewhere sensible. */
export function parseSimpleRule(rrule: string): { freq: SimpleFreq; interval: number } | null {
  if (!rrule.trim()) return { freq: 'MONTHLY', interval: 1 }
  const match = SIMPLE.exec(rrule.trim())
  if (!match) return null
  return { freq: match[1] as SimpleFreq, interval: match[2] ? Number(match[2]) : 1 }
}

export function composeSimpleRule(freq: SimpleFreq, interval: number): string {
  return interval > 1 ? `FREQ=${freq};INTERVAL=${interval}` : `FREQ=${freq}`
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

/** "Every [n] [period]" for the common case, with the raw RRULE behind an Advanced toggle for
 *  everything RFC 5545 can say that the controls cannot. The controls disable themselves
 *  while the rule is one they could not faithfully re-emit. */
export function RecurrenceBuilder({ value, onChange }: { value: string; onChange: (rrule: string) => void }) {
  const simple = parseSimpleRule(value)
  const [advanced, setAdvanced] = useState(simple === null)
  const freq = simple?.freq ?? 'MONTHLY'
  const intervalNumber = simple?.interval ?? 1

  // Edited locally and composed into a rule only once it parses to a whole number >= 1 —
  // clamping on every keystroke (the previous approach) never let the field go empty, so a
  // user who selects-all and retypes (or `userEvent.clear()`) could never actually clear it.
  // Reconciled from the prop on blur and from outside changes while unfocused, the same shape
  // `ChecklistItem`'s number field uses.
  const intervalRef = useRef<HTMLInputElement>(null)
  const [intervalText, setIntervalText] = useState(String(intervalNumber))
  useEffect(() => {
    if (document.activeElement === intervalRef.current) return
    setIntervalText(String(intervalNumber))
  }, [intervalNumber])

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end gap-2">
        <div>
          <label className={LABEL} htmlFor="rrule-interval">Every</label>
          <Input
            ref={intervalRef}
            id="rrule-interval"
            type="number"
            min={1}
            className="w-20"
            value={intervalText}
            disabled={simple === null}
            onChange={(e) => {
              const raw = e.target.value
              setIntervalText(raw)
              const parsed = Number(raw)
              if (raw.trim() !== '' && Number.isInteger(parsed) && parsed >= 1) {
                onChange(composeSimpleRule(freq, parsed))
              }
            }}
            onBlur={() => {
              const parsed = Number(intervalText)
              if (intervalText.trim() === '' || !Number.isInteger(parsed) || parsed < 1) {
                setIntervalText('1')
                onChange(composeSimpleRule(freq, 1))
              }
            }}
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="rrule-freq">Period</label>
          <select
            id="rrule-freq"
            className={SELECT}
            value={freq}
            disabled={simple === null}
            onChange={(e) => onChange(composeSimpleRule(e.target.value as SimpleFreq, intervalNumber))}
          >
            {FREQS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </div>
        <Button variant="ghost" onClick={() => setAdvanced((a) => !a)}>Advanced</Button>
      </div>
      {advanced || simple === null ? (
        <div>
          <label className={LABEL} htmlFor="rrule-raw">RRULE</label>
          <Input id="rrule-raw" value={value} maxLength={500} onChange={(e) => onChange(e.target.value)}
                 placeholder="FREQ=MONTHLY;INTERVAL=3" />
          <p className="mt-1 text-xs text-text3">RFC 5545, without the RRULE: prefix. The start date below anchors it.</p>
        </div>
      ) : null}
    </div>
  )
}
