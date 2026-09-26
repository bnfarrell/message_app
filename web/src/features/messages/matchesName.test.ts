import { describe, expect, it } from 'vitest'
import { matchesName } from './matchesName'

describe('matchesName', () => {
  it('matches any substring, ignoring case', () => {
    expect(matchesName('Eli Engineer', 'eng')).toBe(true)
    expect(matchesName('Eli Engineer', 'ELI E')).toBe(true)
    expect(matchesName('Eli Engineer', 'rosa')).toBe(false)
  })

  it('ignores accents on either side', () => {
    expect(matchesName('José Ruiz', 'jose')).toBe(true)
    expect(matchesName('Jose Ruiz', 'josé')).toBe(true)
  })

  it('treats a blank query as matching everything', () => {
    expect(matchesName('Eli Engineer', '')).toBe(true)
    expect(matchesName('Eli Engineer', '   ')).toBe(true)
  })

  it('trims the query before matching', () => {
    expect(matchesName('Eli Engineer', '  eli  ')).toBe(true)
  })
})
