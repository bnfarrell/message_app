import { act, render, screen } from '@testing-library/react'
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
    // The brief's original assertion here left `vi.advanceTimersByTime` unwrapped, which
    // fails: React 18 schedules the interval's setState via a task fake timers don't
    // advance, so the DOM update never lands before the assertion runs (and logs an
    // act() warning even when it does). Wrapping the advance in `act` is the standard
    // fix and changes no assertion or value.
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.getByText('03:00')).toBeInTheDocument()
  })
})
