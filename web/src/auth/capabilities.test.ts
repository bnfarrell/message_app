import { describe, expect, it } from 'vitest'
import type { Role } from '../api/types'
import { hasCapability, landingPath } from './capabilities'

describe('hasCapability', () => {
  it('lets agents reply but not close work orders', () => {
    expect(hasCapability('agent', 'reply')).toBe(true)
    expect(hasCapability('agent', 'close_work_order')).toBe(false)
  })

  it('lets dept_staff close work orders but not archive conversations', () => {
    expect(hasCapability('dept_staff', 'close_work_order')).toBe(true)
    expect(hasCapability('dept_staff', 'archive')).toBe(false)
  })

  it('keeps dept_staff out of the property-wide conversation list', () => {
    expect(hasCapability('dept_staff', 'view_all_conversations')).toBe(false)
    expect(hasCapability('agent', 'view_all_conversations')).toBe(true)
  })

  it('gives corporate analytics but not reply or admin-side writes', () => {
    expect(hasCapability('corporate', 'view_property_analytics')).toBe(true)
    expect(hasCapability('corporate', 'reply')).toBe(false)
    expect(hasCapability('corporate', 'manage_admin')).toBe(true)
  })

  it('restricts admin screens to admin and corporate', () => {
    const allowed: Role[] = ['admin', 'corporate']
    const denied: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager']
    for (const r of allowed) expect(hasCapability(r, 'manage_admin'), r).toBe(true)
    for (const r of denied) expect(hasCapability(r, 'manage_admin'), r).toBe(false)
  })

  it('lets every staff role add a note', () => {
    const all: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']
    for (const r of all) expect(hasCapability(r, 'add_note'), r).toBe(true)
  })
})

describe('landingPath', () => {
  it('sends each role where §5.2 says', () => {
    expect(landingPath('agent')).toBe('/app/inbox')
    expect(landingPath('dept_staff')).toBe('/app/board?mine=1')
    expect(landingPath('supervisor')).toBe('/app/board?mine=1')
    expect(landingPath('manager')).toBe('/app/analytics')
    expect(landingPath('admin')).toBe('/app/analytics')
    expect(landingPath('corporate')).toBe('/app/analytics')
  })
})
