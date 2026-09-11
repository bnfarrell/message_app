import { describe, expect, it } from 'vitest'
import type { WorkOrderStatus } from '../../api/types'
import { OPEN_STATUSES, TRANSITIONS, allowedTransitions, canTransition } from './transitions'

const ALL: WorkOrderStatus[] = [
  'open', 'assigned', 'in_progress', 'blocked', 'complete', 'verified', 'cancelled',
]

describe('TRANSITIONS', () => {
  it('matches the server matrix exactly', () => {
    expect(TRANSITIONS).toEqual({
      open: ['assigned', 'in_progress', 'cancelled'],
      assigned: ['in_progress', 'open', 'cancelled'],
      in_progress: ['blocked', 'complete', 'cancelled'],
      blocked: ['in_progress', 'cancelled'],
      complete: ['verified', 'in_progress'],
      verified: [],
      cancelled: [],
    })
  })

  it('covers every status, so a new one cannot be silently unhandled', () => {
    for (const status of ALL) expect(TRANSITIONS[status]).toBeDefined()
  })

  it('treats verified and cancelled as terminal', () => {
    expect(allowedTransitions('verified')).toEqual([])
    expect(allowedTransitions('cancelled')).toEqual([])
  })

  it('lets an open order be assigned, started or cancelled — but not completed', () => {
    expect(canTransition('open', 'assigned')).toBe(true)
    expect(canTransition('open', 'in_progress')).toBe(true)
    expect(canTransition('open', 'cancelled')).toBe(true)
    expect(canTransition('open', 'complete')).toBe(false)
    expect(canTransition('open', 'verified')).toBe(false)
    expect(canTransition('open', 'blocked')).toBe(false)
  })

  it('lets an assigned order go back to open — un-assigning is a real move', () => {
    expect(canTransition('assigned', 'open')).toBe(true)
  })

  it('only allows blocked from in_progress', () => {
    expect(canTransition('in_progress', 'blocked')).toBe(true)
    expect(canTransition('assigned', 'blocked')).toBe(false)
    expect(canTransition('blocked', 'blocked')).toBe(false)
  })

  it('lets a complete order be verified or reopened to in_progress, but never cancelled', () => {
    expect(canTransition('complete', 'verified')).toBe(true)
    expect(canTransition('complete', 'in_progress')).toBe(true)
    expect(canTransition('complete', 'cancelled')).toBe(false)
  })

  it('never allows a self-transition', () => {
    for (const status of ALL) expect(canTransition(status, status)).toBe(false)
  })

  it('lists exactly the five open statuses for the board', () => {
    expect(OPEN_STATUSES).toEqual(['open', 'assigned', 'in_progress', 'blocked', 'complete'])
    expect(OPEN_STATUSES).not.toContain('verified')
    expect(OPEN_STATUSES).not.toContain('cancelled')
  })
})
