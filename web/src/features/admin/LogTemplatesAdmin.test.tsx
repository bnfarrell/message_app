import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LogTemplateOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { LogTemplatesAdmin } from './LogTemplatesAdmin'

const NIGHT_AUDIT: LogTemplateOut = {
  id: 't-night',
  name: 'Night Audit',
  shift: 'overnight',
  active: true,
  position: 0,
  usedCount: 6,
  audience: [
    { type: 'user', id: 'u-1' }, { type: 'user', id: 'u-2' }, { type: 'user', id: 'u-3' },
    { type: 'department', id: 'dept-fd' },
  ],
  fields: [
    { id: 'f-occ', position: 0, label: 'Occupancy', fieldType: 'percent', required: true, active: true },
    { id: 'f-notes', position: 1, label: 'Notes', fieldType: 'long_text', required: false, active: true },
  ],
}
const GENERAL: LogTemplateOut = {
  ...NIGHT_AUDIT, id: 't-gen', name: 'General', shift: null, active: false, usedCount: 0, audience: [],
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'POST' || init?.method === 'PATCH') return json(NIGHT_AUDIT, init.method === 'POST' ? 201 : 200)
    if (url.includes('/departments')) return json([aDepartment({ id: 'dept-fd', name: 'Front Desk', type: 'front_desk' })])
    if (url.endsWith('/users')) return json([aStaffUser(), aStaffUser({ id: 'u-off', firstName: 'Old', status: 'disabled' })])
    if (url.includes('/log-templates')) return json([NIGHT_AUDIT, GENERAL])
    return json([])
  })
}

function sent(method: 'POST' | 'PATCH') {
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === method)
  return call ? { url: String(call[0]), body: JSON.parse(String(call[1]!.body)) } : undefined
}

function mount() {
  renderWithProviders(
    <SessionProvider>
      <LogTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

describe('LogTemplatesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists name, shift, field count, who it is shared with, usage and active', async () => {
    mount()
    const night = (await screen.findByText('Night Audit')).closest('tr')!
    expect(within(night).getByText('Overnight')).toBeInTheDocument()
    expect(within(night).getByText('2')).toBeInTheDocument()
    expect(within(night).getByText('3 users, 1 department')).toBeInTheDocument()
    expect(within(night).getByText('6')).toBeInTheDocument()
    expect(within(night).getByText('on')).toBeInTheDocument()
    const general = screen.getByText('General').closest('tr')!
    expect(within(general).getByText('Any')).toBeInTheDocument()
    expect(within(general).getByText('Everyone')).toBeInTheDocument()
    expect(within(general).getByText('off')).toBeInTheDocument()
  })

  it('creates a template with ordered fields and an audience', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
    await userEvent.type(screen.getByLabelText('Name'), 'AM Checklist')
    await userEvent.selectOptions(screen.getByLabelText('Shift'), 'am')
    await userEvent.click(screen.getByRole('button', { name: 'Add field' }))
    await userEvent.type(screen.getByLabelText('Label for field 1'), 'Walk-ins')
    await userEvent.click(screen.getByRole('button', { name: 'Add field' }))
    await userEvent.type(screen.getByLabelText('Label for field 2'), 'Occupancy')
    await userEvent.selectOptions(screen.getByLabelText('Type for field 2'), 'percent')
    await userEvent.click(screen.getByRole('button', { name: 'Move field 2 up' }))
    await userEvent.click(screen.getByLabelText('Field 2 required'))
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Front Desk' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Ava Nolan' }))
    expect(screen.queryByRole('checkbox', { name: /Old/ })).not.toBeInTheDocument() // disabled
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(sent('POST')?.body).toEqual({
      name: 'AM Checklist', shift: 'am', active: true,
      fields: [
        { label: 'Occupancy', fieldType: 'percent', required: true },
        { label: 'Walk-ins', fieldType: 'integer', required: false },
      ],
      audience: [{ type: 'department', id: 'dept-fd' }, { type: 'user', id: 'u-ava' }],
    }))
    expect(sent('POST')!.url).toBe('/api/p/prop-a/log-templates')
  })

  it('edits a saved template: its field types are locked and ids ride along', async () => {
    mount()
    await userEvent.click(await screen.findByText('Night Audit'))
    expect(screen.getByLabelText('Type for field 1')).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Add field' }))
    expect(screen.getByLabelText('Type for field 3')).not.toBeDisabled()
    await userEvent.type(screen.getByLabelText('Label for field 3'), 'Walk-ins')
    await userEvent.click(screen.getByRole('button', { name: 'Remove field 2' }))
    await userEvent.selectOptions(screen.getByLabelText('Shift'), '')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(sent('PATCH')).toBeDefined())
    expect(sent('PATCH')!.url).toBe('/api/p/prop-a/log-templates/t-night')
    expect(sent('PATCH')!.body).toMatchObject({
      name: 'Night Audit', shift: null,
      fields: [
        { id: 'f-occ', label: 'Occupancy', fieldType: 'percent', required: true },
        { label: 'Walk-ins', fieldType: 'integer', required: true },
      ],
    })
    expect(sent('PATCH')!.body.audience).toHaveLength(4)
  })

  it('shows an inline error and refuses to save a blank name', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Name is required')).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)

    await userEvent.type(screen.getByLabelText('Name'), 'AM Checklist')
    expect(screen.queryByText('Name is required')).not.toBeInTheDocument()
  })

  it('shows a server field error under the field list', async () => {
    vi.mocked(fetch).mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return json({ error: { code: 'VALIDATION_FAILED', message: 'Every field needs a label',
                               details: { fields: 'required' } } }, 400)
      }
      return json([])
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
    await userEvent.type(screen.getByLabelText('Name'), 'X')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('This field is required.')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Every field needs a label')
  })
})
