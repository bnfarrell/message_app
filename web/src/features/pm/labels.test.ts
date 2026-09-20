import { describe, expect, it } from 'vitest'
import { formatWindow, isKind, ordinal } from './labels'

describe('pm labels', () => {
  it('ordinal handles the teens', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23].map(ordinal)).toEqual([
      '1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd',
    ])
  })

  it('formats a cycle window from calendar parts, not instants', () => {
    expect(formatWindow('2026-07-01', '2026-09-30')).toBe('Jul 01 – Sep 30')
  })

  it('isKind narrows', () => {
    expect(isKind('guest_room')).toBe(true)
    expect(isKind('all')).toBe(false)
    expect(isKind(null)).toBe(false)
  })
})
