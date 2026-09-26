import { describe, expect, it } from 'vitest'
import { hasCapability } from '../auth/capabilities'
import { NAV_GROUPS, isNavItemActive, visibleNavGroups } from './navModel'

const item = (label: string) =>
  NAV_GROUPS.flatMap((group) => group.items).find((i) => i.label === label)!

describe('isNavItemActive', () => {
  it('lights a section entry on every screen inside it, not only on its own target', () => {
    const admin = item('Admin')
    expect(admin.to).toBe('/app/admin/users')
    expect(isNavItemActive(admin, '/app/admin/users')).toBe(true)
    expect(isNavItemActive(admin, '/app/admin/departments')).toBe(true)
    expect(isNavItemActive(admin, '/app/admin/property')).toBe(true)
  })

  it('compares whole path segments, so a longer name cannot light the entry', () => {
    // A bare startsWith would light Admin on /app/administration.
    expect(isNavItemActive(item('Admin'), '/app/administration')).toBe(false)
    expect(isNavItemActive(item('Board'), '/app/boardroom')).toBe(false)
  })

  it('falls back to `to` for an entry with no `match`', () => {
    const inbox = item('Inbox')
    expect(inbox.match).toBeUndefined()
    expect(isNavItemActive(inbox, '/app/inbox')).toBe(true)
    expect(isNavItemActive(inbox, '/app/inbox/c-1')).toBe(true)
    expect(isNavItemActive(inbox, '/app/board')).toBe(false)
  })
})

describe('checklists navigation', () => {
  it('puts Checklists in Overview after Log', () => {
    const overview = NAV_GROUPS.find((g) => g.heading === 'Overview')!
    const labels = overview.items.map((i) => i.label)
    expect(labels.indexOf('Checklists')).toBe(labels.indexOf('Log') + 1)
    const item = overview.items.find((i) => i.label === 'Checklists')!
    expect(isNavItemActive(item, '/app/checklists/abc')).toBe(true)
  })
})

describe('visibleNavGroups', () => {
  it('shows the Log entry to every staff role', () => {
    const groups = visibleNavGroups(() => false) // no capabilities at all
    const items = groups.flatMap((g) => g.items)
    expect(items.find((i) => i.to === '/app/log')).toBeTruthy()
  })
})

describe('maintenance group', () => {
  it('shows Preventative Maintenance to view_pm holders and PM Inspection to inspect_pm holders', () => {
    const only = (cap: string) => visibleNavGroups((c) => c === cap)
    expect(only('view_pm').flatMap((g) => g.items).map((i) => i.label)).toContain('Preventative Maintenance')
    expect(only('view_pm').flatMap((g) => g.items).map((i) => i.label)).not.toContain('PM Inspection')
    expect(only('inspect_pm').flatMap((g) => g.items).map((i) => i.label)).toContain('PM Inspection')
  })

  it('lights the PM entry on runs and compliance but not on the inspection queue', () => {
    const pm = item('Preventative Maintenance')
    expect(isNavItemActive(pm, '/app/pm')).toBe(true)
    expect(isNavItemActive(pm, '/app/pm/runs/run-1')).toBe(true)
    expect(isNavItemActive(pm, '/app/pm/compliance')).toBe(true)
    expect(isNavItemActive(pm, '/app/inspection')).toBe(false)
    expect(isNavItemActive(item('PM Inspection'), '/app/inspection')).toBe(true)
  })
})

describe('housekeeping navigation', () => {
  it('sits above Maintenance and keeps Room Inspection from lighting Rooms', () => {
    const at = NAV_GROUPS.findIndex((g) => g.heading === 'Housekeeping')
    expect(NAV_GROUPS[at + 1]!.heading).toBe('Maintenance')
    const items = NAV_GROUPS[at]!.items
    expect(items.map((i) => i.to)).toEqual(['/app/housekeeping', '/app/my-rooms', '/app/room-inspection'])
    expect(isNavItemActive(items[0]!, '/app/room-inspection')).toBe(false)
    expect(isNavItemActive(items[0]!, '/app/housekeeping')).toBe(true)
  })

  it('shows front desk the board only', () => {
    const groups = visibleNavGroups((c) => hasCapability('agent', c))
    const hk = groups.find((g) => g.heading === 'Housekeeping')!
    expect(hk.items.map((i) => i.label)).toEqual(['Rooms'])
  })
})
