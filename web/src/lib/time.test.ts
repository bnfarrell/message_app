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
