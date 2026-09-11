import { describe, expect, it } from 'vitest'
import { presenceLine } from './ConversationHeader'

describe('presenceLine', () => {
  it('names a single viewer', () => {
    expect(presenceLine(['Marcus'], false)).toBe('Marcus is viewing')
  })

  it('says replying when someone is composing', () => {
    expect(presenceLine(['Marcus'], true)).toBe('Marcus is replying')
  })

  it('collapses two people to one other', () => {
    expect(presenceLine(['Marcus', 'Jordan'], false)).toBe('Marcus and 1 other are viewing')
  })

  it('pluralises beyond two', () => {
    expect(presenceLine(['Marcus', 'Jordan', 'Ava'], false)).toBe('Marcus and 2 others are viewing')
  })

  it('returns an empty string for nobody, so the caller renders no chip', () => {
    expect(presenceLine([], false)).toBe('')
  })
})
