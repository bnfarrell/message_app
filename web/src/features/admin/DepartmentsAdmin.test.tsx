import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { DepartmentsAdmin } from './DepartmentsAdmin'

// Names deliberately unlike their own type labels, so a query for a label cannot accidentally
// match a name and pass for the wrong reason.
const DEPARTMENTS = [
  aDepartment({ id: 'dept-eng', name: 'Maintenance', type: 'engineering', escalationMinutes: 20 }),
  aDepartment({ id: 'dept-fd', name: 'Reception', type: 'front_desk', escalationMinutes: 10 }),
]

function json(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** `override` claims a specific request; anything it declines falls through to the happy path. */
function serve(override?: (url: string, init?: RequestInit) => Response | null) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const claimed = override?.(url, init)
    if (claimed) return Promise.resolve(claimed)
    if (init?.method === 'DELETE') return Promise.resolve(json(null, 204))
    if (init?.method && init.method !== 'GET') return Promise.resolve(json(aDepartment()))
    return Promise.resolve(json(DEPARTMENTS))
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <DepartmentsAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/departments' },
  )
}

const writes = (method: string) =>
  vi.mocked(fetch).mock.calls.filter(([, i]) => i?.method === method)

describe('DepartmentsAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists departments with a human type label, not the raw enum value', async () => {
    mount()
    expect(await screen.findByText('Maintenance')).toBeInTheDocument()
    expect(screen.getByText('Maintenance')).toBeInTheDocument() // the type of the row above
    expect(screen.getByText('Front desk')).toBeInTheDocument()
    expect(screen.queryByText('front_desk')).not.toBeInTheDocument()
  })

  it('creates a department, defaulting the type to other rather than to a routing role', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new department/i }))
    await user.type(screen.getByLabelText('Name'), 'Spa')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const [url, init] = writes('POST')[0]!
    expect(String(url)).toMatch(/\/departments$/)
    // `other` because Department.type is load-bearing: notifications.py routes to the `front_desk`
    // department, so defaulting there would silently make every new department a notification
    // target. escalationMinutes is absent — DepartmentIn defaults it, and D81 keeps it off the form.
    expect(JSON.parse(String(init!.body))).toEqual({ name: 'Spa', type: 'other', active: true })
  })

  it('offers every department type the server accepts', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new department/i }))
    for (const label of ['Front desk', 'Housekeeping', 'Engineering', 'Food & beverage',
                         'Spa', 'Security', 'Valet', 'Other']) {
      expect(screen.getByRole('option', { name: label })).toBeInTheDocument()
    }
  })

  it('will not POST a department with no name', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /new department/i }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(writes('POST')).toHaveLength(0)
  })

  it('patches name, type and active on an existing row', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Maintenance'))
    await user.selectOptions(await screen.findByLabelText('Type'), 'spa')
    await user.click(screen.getByLabelText('Active'))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const [url, init] = writes('PATCH')[0]!
    expect(String(url)).toContain('/departments/dept-eng')
    expect(JSON.parse(String(init!.body))).toEqual({
      name: 'Maintenance', type: 'spa', active: false,
    })
  })

  it('deletes a department, then refetches the list every picker in the product reads', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Maintenance'))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    const reads = () =>
      vi.mocked(fetch).mock.calls.filter(([, i]) => !i?.method || i.method === 'GET').length
    const before = reads()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(String(writes('DELETE')[0]![0])).toContain('/departments/dept-eng')
    // Department pickers on five other screens read qk.departments; a mutation that skipped the
    // invalidation shows up as a wrong dropdown elsewhere, not as a broken screen here.
    await waitFor(() => expect(reads()).toBeGreaterThan(before))
  })

  it('shows the delete guard’s own message, which names what to fix and the escape hatch', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Maintenance'))
    const conflict =
      'Move the staff members in this department to another one first, or deactivate the ' +
      'department instead'
    serve((_url, init) =>
      init?.method === 'DELETE'
        ? json({ error: { code: 'CONFLICT', message: conflict } }, 409)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    // Verbatim: the server wrote it for an admin to read, and it is the only thing on screen
    // that says which of the five referencing tables is holding the department.
    expect(await screen.findByRole('alert')).toHaveTextContent(conflict)
    // The panel must stay open — the escape hatch it points at is the Active box inside it.
    expect(screen.getByLabelText('Active')).toBeInTheDocument()
  })

  it('pins a field-level 400 to the input that caused it', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Maintenance'))
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Invalid request body',
                          details: [{ loc: ['name'], msg: 'String should have at most 100 characters',
                                      type: 'string_too_long' }] } }, 400)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const message = await screen.findByText('String should have at most 100 characters')
    expect(message.parentElement).toContainElement(screen.getByLabelText('Name'))
  })

  it('drops a failed save when another row is opened', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Maintenance'))
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Invalid request body' } }, 400)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByRole('alert')

    serve()
    await user.click(screen.getByText('Reception'))
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Reception'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows escalation as a column but offers no control for it (D81)', async () => {
    const user = userEvent.setup()
    mount()
    // Displayed, because removing it would regress what already shipped...
    expect(await screen.findByText('20 min')).toBeInTheDocument()
    await user.click(screen.getByText('Maintenance'))
    await screen.findByLabelText('Name')
    // ...and not editable, because nothing in the codebase computes with it: the SLA that is
    // enforced is the property-level slaMinutes. A control that changed nothing would be worse.
    expect(screen.queryByLabelText(/escalation/i)).not.toBeInTheDocument()
    expect(JSON.stringify(writes('PATCH'))).not.toContain('escalationMinutes')
  })
})
