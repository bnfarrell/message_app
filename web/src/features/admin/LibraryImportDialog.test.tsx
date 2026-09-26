import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChecklistLibraryEntryOut, ChecklistTemplateOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistTemplatesAdmin } from './ChecklistTemplatesAdmin'

const LIBRARY: ChecklistLibraryEntryOut[] = [
  { key: 'night_audit', name: 'Night Audit', kind: 'normal', departmentType: 'front_desk',
    categories: [{ name: 'Pre-audit', itemCount: 2 }, { name: 'Handover', itemCount: 2 }], itemCount: 4 },
  { key: 'pool_spa', name: 'Pool & Spa Readings', kind: 'readings', departmentType: 'engineering',
    categories: [], itemCount: 5 },
  { key: 'security_rounds', name: 'Security Rounds', kind: 'normal', departmentType: 'security',
    categories: [], itemCount: 3 },
]

const IMPORTED: ChecklistTemplateOut = {
  id: 't-new', name: 'Night Audit', departmentId: 'dept-fd', departmentName: 'Front Desk',
  schedule: 'unscheduled', shift: null, weekdays: null, active: true, kind: 'normal',
  categories: [{ id: 'c-pre', name: 'Pre-audit', position: 0 }],
  items: [{ id: 'i-1', position: 0, label: 'No-shows posted', itemType: 'checkbox', unit: null,
            minValue: null, maxValue: null, required: true, active: true, categoryId: 'c-pre' }],
}

let importStatus = 201

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const reply = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status }))
    if (url.includes('/departments')) {
      return reply([aDepartment(), aDepartment({ id: 'dept-fd', name: 'Front Desk', type: 'front_desk' })])
    }
    if (url.endsWith('/checklists/library')) return reply(LIBRARY)
    if (url.includes('/import')) {
      return importStatus === 201
        ? reply(IMPORTED, 201)
        : reply({ error: { code: 'VALIDATION_FAILED', message: 'Unknown department',
                           details: { departmentId: 'unknown' } } }, importStatus)
    }
    return reply([])
  })
}

function mount() {
  renderWithProviders(
    <SessionProvider>
      <ChecklistTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

function importCall() {
  const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes('/import'))
  return call ? { url: String(call[0]), body: JSON.parse(String(call[1]!.body)) } : undefined
}

describe('Import from library', () => {
  beforeEach(() => {
    importStatus = 201
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists the starter checklists with their kind, categories and item count', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Import from library' }))
    expect(await screen.findByText('Pool & Spa Readings')).toBeInTheDocument()
    expect(screen.getByText('Pre-audit · Handover — 4 items')).toBeInTheDocument()
    expect(screen.getByText('5 items')).toBeInTheDocument()
    expect(screen.getByText('Readings')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
  })

  it('imports into the chosen department and opens the copy in the editor', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Import from library' }))
    await user.click(await screen.findByRole('radio', { name: /Night Audit/ }))
    // the entry's department type is suggested
    expect(screen.getByLabelText('Department', { selector: '#library-dept' })).toHaveValue('dept-fd')
    await user.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(importCall()).toEqual({
      url: '/api/p/prop-a/checklists/library/night_audit/import', body: { departmentId: 'dept-fd' } }))
    expect(await screen.findByText('Edit template')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Import from library' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveValue('Night Audit')
    expect(screen.getByRole('radio', { name: 'Not scheduled yet' })).toBeChecked()
    expect(screen.getByLabelText('Name for category 1')).toHaveValue('Pre-audit')
  })

  it('clears the department when the newly chosen entry matches none', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Import from library' }))
    await user.click(await screen.findByRole('radio', { name: /Night Audit/ }))
    expect(screen.getByLabelText('Department', { selector: '#library-dept' })).toHaveValue('dept-fd')
    await user.click(await screen.findByRole('radio', { name: /Security Rounds/ }))
    expect(screen.getByLabelText('Department', { selector: '#library-dept' })).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
  })

  it('shows a refused import inside the dialog', async () => {
    importStatus = 400
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Import from library' }))
    await user.click(await screen.findByRole('radio', { name: /Night Audit/ }))
    await user.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unknown department')
    expect(screen.getByRole('dialog', { name: 'Import from library' })).toBeInTheDocument()
  })
})
