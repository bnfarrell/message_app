import { describe, expect, it } from 'vitest'
import { rangeFor } from './dateRange'

const NOW = new Date(2026, 8, 10, 19, 4) // 10 Sep 2026, local

describe('rangeFor', () => {
  it('makes today a single inclusive day', () => {
    expect(rangeFor('today', NOW)).toEqual({ from: '2026-09-10', to: '2026-09-10' })
  })

  it('makes 7 days span seven days including today, not eight', () => {
    expect(rangeFor('7d', NOW)).toEqual({ from: '2026-09-04', to: '2026-09-10' })
  })

  it('makes 30 days span thirty days including today', () => {
    expect(rangeFor('30d', NOW)).toEqual({ from: '2026-08-12', to: '2026-09-10' })
  })

  it('crosses a month boundary correctly', () => {
    expect(rangeFor('7d', new Date(2026, 8, 2, 12, 0))).toEqual({
      from: '2026-08-27',
      to: '2026-09-02',
    })
  })

  it('crosses a year boundary correctly', () => {
    expect(rangeFor('7d', new Date(2027, 0, 3, 12, 0))).toEqual({
      from: '2026-12-28',
      to: '2027-01-03',
    })
  })

  it('uses local date parts, so a late-evening call does not roll to tomorrow', () => {
    expect(rangeFor('today', new Date(2026, 8, 10, 23, 59)).to).toBe('2026-09-10')
  })

  it('uses the custom from/to when key is custom', () => {
    expect(rangeFor('custom', NOW, '2026-08-01', '2026-08-15')).toEqual({
      from: '2026-08-01',
      to: '2026-08-15',
    })
  })

  it('falls back to a 30-day window if custom is selected but no dates are given', () => {
    expect(rangeFor('custom', NOW)).toEqual({ from: '2026-08-12', to: '2026-09-10' })
  })
})
