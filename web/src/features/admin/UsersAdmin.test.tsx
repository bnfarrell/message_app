import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { UsersAdmin } from './UsersAdmin'

const STAFF = [
  aStaffUser({ id: 'u-ava', firstName: 'Ava', lastName: 'Nolan', role: 'agent' }),
  aStaffUser({
    id: 'u-eli',
    firstName: 'Eli',
    lastName: 'Engineer',
    email: 'eli@hvh.test',
    role: 'dept_staff',
    departmentId: 'dept-eng',
  }),
]

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    if (init && init.method && init.method !== 'GET') {
      return Promise.resolve(
        new Response(JSON.stringify(aStaffUser()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = String(input).includes('/departments') ? [aDepartment()] : STAFF
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <UsersAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/users' },
  )
}

describe('UsersAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists staff with name, email, role and department', async () => {
    mount()
    expect(await screen.findByText('Ava Nolan')).toBeInTheDocument()
    expect(screen.getByText('ava@hvh.test')).toBeInTheDocument()
    expect(screen.getAllByText(/agent/i).length).toBeGreaterThan(0)
    expect(screen.getByText('Engineering')).toBeInTheDocument()
  })

  it('offers every role in the enum when editing', async () => {
    mount()
    await userEvent.click(await screen.findByText('Ava Nolan'))
    const select = await screen.findByLabelText('Role')
    for (const role of ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']) {
      expect(screen.getByRole('option', { name: role })).toBeInTheDocument()
    }
    expect(select).toHaveValue('agent')
  })

  it('patches the role', async () => {
    mount()
    await userEvent.click(await screen.findByText('Ava Nolan'))
    await userEvent.selectOptions(await screen.findByLabelText('Role'), 'supervisor')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(String(patch![0])).toContain('/users/u-ava')
    expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ role: 'supervisor' })
  })

  it('creates a user with the required identity fields', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /new user/i }))
    await userEvent.type(screen.getByLabelText('First name'), 'Nia')
    await userEvent.type(screen.getByLabelText('Last name'), 'Okafor')
    await userEvent.type(screen.getByLabelText('Email'), 'nia@hvh.test')
    await userEvent.selectOptions(screen.getByLabelText('Role'), 'agent')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({
      firstName: 'Nia',
      lastName: 'Okafor',
      email: 'nia@hvh.test',
      role: 'agent',
    })
  })

  it('will not create a user without an email', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /new user/i }))
    await userEvent.type(screen.getByLabelText('First name'), 'Nia')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })
  // EditPanel's delete confirmation is local state and the panel is never unmounted between
  // records, so without a subject-scoped reset an arming survives the change of subject.
  it('does not carry an armed delete confirmation to another user', async () => {
    mount()
    await userEvent.click(await screen.findByText('Ava Nolan'))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument()

    await userEvent.click(screen.getByText('Eli Engineer'))
    await waitFor(() => expect(screen.getByLabelText('Role')).toHaveValue('dept_staff'))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('does not carry it across a New user, which hides the delete controls without dismissing them', async () => {
    mount()
    await userEvent.click(await screen.findByText('Ava Nolan'))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    // `onDelete` is undefined for an unsaved record, so the delete row disappears entirely and
    // the admin reasonably believes the confirmation is gone with it.
    await userEvent.click(screen.getByRole('button', { name: /new user/i }))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('Eli Engineer'))
    await waitFor(() => expect(screen.getByLabelText('Role')).toHaveValue('dept_staff'))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })
})
