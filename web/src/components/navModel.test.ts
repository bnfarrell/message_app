import { describe, expect, it } from 'vitest'
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

describe('visibleNavGroups', () => {
  it('shows the Log entry to every staff role', () => {
    const groups = visibleNavGroups(() => false) // no capabilities at all
    const items = groups.flatMap((g) => g.items)
    expect(items.find((i) => i.to === '/app/log')).toBeTruthy()
  })
})
