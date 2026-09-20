import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { TemplateOut, UnitOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { PmTemplatesAdmin } from './PmTemplatesAdmin'

const TEMPLATE: TemplateOut = {
  id: 't-1', name: 'Guest Room Quarterly', mode: 'sweep', departmentId: 'dept-eng', active: true,
  unitKind: 'guest_room', cadence: 'quarterly', rrule: null, rruleDtstart: null, lastFiredAt: null,
  unitIds: [], hasRuns: true, createdAt: '2026-09-01T00:00:00Z',
  items: [
    { id: 'i-1', position: 0, label: 'HVAC filter replaced', itemType: 'checkbox', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
  ],
}
const BOILER: UnitOut = {
  id: 'u-b1', kind: 'equipment', code: 'BOILER-1', name: 'Boiler 1', floor: null, roomType: null,
  active: true, source: 'manual', externalId: null, notes: null, createdAt: '2026-09-01T00:00:00Z',
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/departments')) return json([aDepartment()])
    if (url.includes('maintainable-units')) return json([BOILER])
    if (init?.method === 'POST') return json({ ...TEMPLATE, id: 't-new' }, 201)
    if (init?.method === 'PATCH') return json(TEMPLATE)
    return json([TEMPLATE])
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <PmTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

describe('PmTemplatesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('locks the mode on a template with runs and keeps item types fixed', async () => {
    serve()
    mount()
    await userEvent.click(await screen.findByText('Guest Room Quarterly'))
    expect(screen.getByLabelText('Mode')).toBeDisabled()
    expect(screen.getByLabelText('Cadence')).toHaveValue('quarterly')
    expect(screen.getByDisplayValue('HVAC filter replaced')).toBeInTheDocument()
    expect(screen.getByLabelText('Type for item 1')).toBeDisabled()
  })

  it('creates a scheduled template with a composed RRULE, targets and items', async () => {
    serve()
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Boiler inspection')
    await userEvent.selectOptions(screen.getByLabelText('Mode'), 'scheduled')
    await userEvent.clear(screen.getByLabelText('Every'))
    await userEvent.type(screen.getByLabelText('Every'), '3')
    await userEvent.type(screen.getByLabelText('Starts on'), '2026-07-01')
    await userEvent.click(await screen.findByRole('checkbox', { name: /Boiler 1/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Add item' }))
    await userEvent.type(screen.getByLabelText('Label for item 1'), 'Pressure')
    await userEvent.selectOptions(screen.getByLabelText('Type for item 1'), 'number')
    await userEvent.type(screen.getByLabelText('Unit for item 1'), 'psi')
    await userEvent.type(screen.getByLabelText('Min for item 1'), '10')
    await userEvent.type(screen.getByLabelText('Max for item 1'), '30')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')!
      expect(JSON.parse(String(post[1]!.body))).toEqual({
        name: 'Boiler inspection', mode: 'scheduled', departmentId: null, active: true,
        unitKind: null, cadence: null, rrule: 'FREQ=MONTHLY;INTERVAL=3', rruleDtstart: '2026-07-01',
        unitIds: ['u-b1'],
        items: [{ label: 'Pressure', itemType: 'number', unit: 'psi', minValue: 10, maxValue: 30, required: true }],
      })
    })
  })
})
