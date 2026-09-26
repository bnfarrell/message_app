import { describe, expect, it } from 'vitest'
import { audienceSummary, formatFieldValue } from './templates'

describe('formatFieldValue', () => {
  it('shows a percent with its sign and drops trailing zeros', () => {
    expect(formatFieldValue({ fieldId: 'f', label: 'Occupancy', fieldType: 'percent', numberValue: 87 })).toBe('87%')
    expect(formatFieldValue({ fieldId: 'f', label: 'Occupancy', fieldType: 'percent', numberValue: 87.5 })).toBe('87.5%')
    expect(formatFieldValue({ fieldId: 'f', label: 'ADR', fieldType: 'decimal', numberValue: 129.4 })).toBe('129.4')
    expect(formatFieldValue({ fieldId: 'f', label: 'Walk-ins', fieldType: 'integer', numberValue: 3 })).toBe('3')
  })

  it('shows text as written', () => {
    expect(formatFieldValue({ fieldId: 'f', label: 'Notes', fieldType: 'long_text', textValue: 'Quiet' })).toBe('Quiet')
  })
})

describe('audienceSummary', () => {
  it('says Everyone for an empty audience and counts users and departments otherwise', () => {
    expect(audienceSummary([])).toBe('Everyone')
    expect(audienceSummary([
      { type: 'user', id: 'u-1' }, { type: 'user', id: 'u-2' }, { type: 'user', id: 'u-3' },
      { type: 'department', id: 'd-1' },
    ])).toBe('3 users, 1 department')
    expect(audienceSummary([{ type: 'department', id: 'd-1' }, { type: 'department', id: 'd-2' }]))
      .toBe('2 departments')
  })
})
