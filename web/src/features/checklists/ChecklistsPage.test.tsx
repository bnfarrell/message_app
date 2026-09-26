import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { ChecklistInstanceRowOut, ChecklistTemplateOut, Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistsPage } from './ChecklistsPage'

function row(over: Partial<ChecklistInstanceRowOut>): ChecklistInstanceRowOut {
  return {
    id: 'i-am', templateId: 't-am', templateName: 'Engineering AM Rounds',
    departmentId: 'dept-eng', departmentName: 'Engineering', dueDate: '2026-09-10', shift: 'am',
    onDemand: false, status: 'open', kind: 'normal', assignedUserId: null, assignedName: null,
    completedByName: null, done: 0, total: 3, outOfRangeCount: 0, ...over,
  }
}

const TODAY = [
  row({}),
  row({ id: 'i-pm', templateId: 't-pm', templateName: 'Engineering PM Walk', shift: 'pm',
        status: 'in_progress', assignedUserId: 'u-eli', assignedName: 'Eli Engineer', done: 2,
        total: 5, outOfRangeCount: 1 }),
]
const ON_DEMAND: ChecklistTemplateOut = {
  id: 't-out', name: 'Power Outage', departmentId: 'dept-eng', departmentName: 'Engineering',
  schedule: 'on_demand', shift: null, weekdays: null, active: true, kind: 'normal',
  categories: [], items: [],
}
const MISSED = [row({ id: 'i-old', dueDate: '2026-09-09', status: 'missed',
                      templateName: 'Housekeeping PM Linen Par' })]

const calls: { url: string; method: string }[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ url, method })
    const body = url.includes('/departments') ? [aDepartment()]
      : url.includes('staff-directory') ? []
      : url.includes('/checklists/missed') ? MISSED
      : url.includes('/checklists/templates') && method === 'GET' ? [ON_DEMAND]
      : method === 'POST' ? { ...row({}), id: url.includes('/templates/') ? 'i-new' : 'i-am' }
      : TODAY
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  })
}

function mount(role: Role) {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/checklists" element={<ChecklistsPage />} />
        <Route path="/app/checklists/:id" element={<p>checklist page</p>} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role, departmentId: 'dept-eng' }), route: '/app/checklists' },
  )
}

describe('ChecklistsPage', () => {
  beforeEach(() => {
    calls.length = 0
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('groups today by shift with progress and an out-of-range flag', async () => {
    mount('dept_staff')
    await screen.findByText('Engineering PM Walk')
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent))
      .toEqual(['AM', 'PM'])
    const pm = screen.getByText('Engineering PM Walk').closest('li')!
    expect(within(pm).getByText('2 / 5')).toBeInTheDocument()
    expect(within(pm).getByText('Eli Engineer')).toBeInTheDocument()
    expect(within(pm).getByText('1 out of range')).toBeInTheDocument()
  })

  it('asks the server for my department by default', async () => {
    mount('dept_staff')
    await screen.findByText('Engineering AM Rounds')
    expect(calls.some((c) => c.url.includes('/checklists/instances')
      && c.url.includes('departmentId=dept-eng'))).toBe(true)
  })

  it('starts an open checklist and opens it', async () => {
    const user = userEvent.setup()
    mount('dept_staff')
    const am = (await screen.findByText('Engineering AM Rounds')).closest('li')!
    await user.click(within(am).getByRole('button', { name: 'Start' }))
    expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/instances/i-am/start')))
      .toBe(true)
    expect(await screen.findByText('checklist page')).toBeInTheDocument()
  })

  it('shows Assign and Missed only to supervisors and above', async () => {
    const staff = mount('dept_staff')
    await screen.findByText('Engineering AM Rounds')
    expect(screen.queryByLabelText('Assign Engineering AM Rounds')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Missed' })).not.toBeInTheDocument()
    staff.unmount()

    const sup = mount('supervisor')
    expect(await screen.findByLabelText('Assign Engineering AM Rounds')).toBeInTheDocument()
    expect(await screen.findByRole('tab', { name: 'Missed' })).toBeInTheDocument()
    sup.unmount()

    const user = userEvent.setup()
    mount('manager')
    await user.click(await screen.findByRole('tab', { name: 'Missed' }))
    expect(await screen.findByText('Housekeeping PM Linen Par')).toBeInTheDocument()
  })

  it('shows an inline error when assigning fails', async () => {
    const user = userEvent.setup()
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ url, method })
      if (url.endsWith('/instances/i-am/assign')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ error: { code: 'VALIDATION_FAILED', message: 'Not on this shift' } }),
            { status: 400 },
          ),
        )
      }
      const body = url.includes('/departments') ? [aDepartment()]
        : url.includes('staff-directory') ? [
            { userId: 'u-eli', firstName: 'Eli', lastName: 'Engineer', role: 'dept_staff',
              departmentId: 'dept-eng' },
          ]
        : url.includes('/checklists/missed') ? MISSED
        : url.includes('/checklists/templates') && method === 'GET' ? [ON_DEMAND]
        : TODAY
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    })
    mount('supervisor')
    const am = (await screen.findByText('Engineering AM Rounds')).closest('li')!
    await within(am).findByText('Eli Engineer')
    await user.selectOptions(within(am).getByLabelText('Assign Engineering AM Rounds'), 'u-eli')
    expect(await within(am).findByRole('alert')).toHaveTextContent('Not on this shift')
  })

  it('sends userId: null, not an empty string, when unassigning', async () => {
    const user = userEvent.setup()
    const bodies: unknown[] = []
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ url, method })
      if (url.endsWith('/instances/i-am/assign')) {
        bodies.push(JSON.parse(String(init?.body)))
        return Promise.resolve(new Response(JSON.stringify(row({ assignedUserId: null })),
          { status: 200 }))
      }
      const body = url.includes('/departments') ? [aDepartment()]
        : url.includes('staff-directory') ? [
            { userId: 'u-eli', firstName: 'Eli', lastName: 'Engineer', role: 'dept_staff',
              departmentId: 'dept-eng' },
          ]
        : url.includes('/checklists/missed') ? MISSED
        : url.includes('/checklists/templates') && method === 'GET' ? [ON_DEMAND]
        : [row({ assignedUserId: 'u-eli', assignedName: 'Eli Engineer' }), TODAY[1]!]
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    })
    mount('supervisor')
    const am = (await screen.findByText('Engineering AM Rounds')).closest('li')!
    await within(am).findByText('Eli Engineer')
    await user.selectOptions(within(am).getByLabelText('Assign Engineering AM Rounds'), 'Unassigned')
    await waitFor(() => expect(bodies).toEqual([{ userId: null }]))
  })

  it('does not offer Start for another department\'s row when viewing all departments', async () => {
    const user = userEvent.setup()
    const frontDesk = row({
      id: 'i-fd', templateId: 't-fd', templateName: 'Front Desk Opening',
      departmentId: 'dept-fd', departmentName: 'Front Desk', shift: 'am',
    })
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ url, method })
      const body = url.includes('/departments')
          ? [aDepartment(), aDepartment({ id: 'dept-fd', name: 'Front Desk' })]
        : url.includes('staff-directory') ? []
        : url.includes('/checklists/missed') ? MISSED
        : url.includes('/checklists/templates') && method === 'GET' ? [ON_DEMAND]
        : method === 'POST' ? { ...row({}), id: 'i-am' }
        : [...TODAY, frontDesk]
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    })
    mount('dept_staff')
    await screen.findByText('Engineering AM Rounds')
    await user.selectOptions(screen.getByLabelText('Department'), '')
    const fd = (await screen.findByText('Front Desk Opening')).closest('li')!
    expect(within(fd).queryByRole('button', { name: 'Start' })).not.toBeInTheDocument()
    expect(within(fd).getByRole('button', { name: 'View' })).toBeInTheDocument()
    const eng = (await screen.findByText('Engineering AM Rounds')).closest('li')!
    expect(within(eng).getByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('starts an on-demand checklist from the menu', async () => {
    const user = userEvent.setup()
    mount('dept_staff')
    await user.selectOptions(await screen.findByLabelText('Start a checklist'), 't-out')
    await waitFor(() => expect(calls.some(
      (c) => c.method === 'POST' && c.url.endsWith('/templates/t-out/start'))).toBe(true))
    expect(await screen.findByText('checklist page')).toBeInTheDocument()
  })
})
