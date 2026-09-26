import { describe, expect, it } from 'vitest'
import { groupByCategory } from './grouping'
import { KIND_LABELS, scheduleLabel } from './labels'

const CATEGORIES = [
  { id: 'c-audit', name: 'Audit', position: 0, done: 1, total: 2 },
  { id: 'c-pay', name: 'Payments', position: 1, done: 0, total: 1 },
]

describe('groupByCategory', () => {
  it('puts ungrouped items first and keeps each group in the server order', () => {
    const items = [
      { id: 'a', categoryId: 'c-audit' },
      { id: 'n', categoryId: null },
      { id: 'p', categoryId: 'c-pay' },
      { id: 'b', categoryId: 'c-audit' },
    ]
    const { ungrouped, groups } = groupByCategory(items, CATEGORIES)
    expect(ungrouped.map((i) => i.id)).toEqual(['n'])
    expect(groups.map((g) => [g.name, g.done, g.total, g.items.map((i) => i.id)])).toEqual([
      ['Audit', 1, 2, ['a', 'b']],
      ['Payments', 0, 1, ['p']],
    ])
  })

  it('never drops an item whose category is not listed', () => {
    const { ungrouped } = groupByCategory([{ id: 'x', categoryId: 'c-gone' }, { id: 'y' }], [])
    expect(ungrouped.map((i) => i.id)).toEqual(['x', 'y'])
  })
})

describe('schedule and kind labels', () => {
  it('reads an unscheduled template as a call to action', () => {
    expect(scheduleLabel({ schedule: 'unscheduled', shift: null, weekdays: null })).toBe('Set schedule')
    expect(scheduleLabel({ schedule: 'on_demand' })).toBe('On demand')
    expect(scheduleLabel({ schedule: 'weekly', shift: 'am', weekdays: 127 })).toBe('AM · Every day')
    expect(KIND_LABELS.readings).toBe('Readings')
  })
})
