import { describe, expect, it } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('joins truthy parts with a single space', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('drops false, null and undefined so conditionals read inline', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b')
  })

  it('returns an empty string when everything is falsy', () => {
    expect(cn(false, undefined)).toBe('')
  })
})
