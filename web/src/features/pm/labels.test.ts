import { describe, expect, it } from 'vitest'
import { formatWindow, isKind } from './labels'

describe('pm labels', () => {
  it('formats a cycle window from calendar parts, not instants', () => {
    expect(formatWindow('2026-07-01', '2026-09-30')).toBe('Jul 01 – Sep 30')
  })

  it('isKind narrows', () => {
    expect(isKind('guest_room')).toBe(true)
    expect(isKind('all')).toBe(false)
    expect(isKind(null)).toBe(false)
  })
})
