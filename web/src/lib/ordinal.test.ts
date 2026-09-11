import { describe, expect, it } from 'vitest'
import { ordinal } from './ordinal'

describe('ordinal', () => {
  it('uses st/nd/rd for 1, 2, 3 and th for the rest', () => {
    expect([1, 2, 3, 4, 5].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '5th'])
  })

  it('takes th for 11, 12 and 13, which is the trap', () => {
    expect([11, 12, 13].map(ordinal)).toEqual(['11th', '12th', '13th'])
  })

  it('goes back to st/nd/rd at 21, 22, 23 and again at 101', () => {
    expect([21, 22, 23, 101, 111, 112].map(ordinal)).toEqual([
      '21st',
      '22nd',
      '23rd',
      '101st',
      '111th',
      '112th',
    ])
  })

  it('handles a zeroth and a first stay', () => {
    expect(ordinal(0)).toBe('0th')
    expect(ordinal(1)).toBe('1st')
  })
})
