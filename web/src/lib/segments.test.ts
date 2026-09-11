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
