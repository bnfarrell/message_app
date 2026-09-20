import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { UnitOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { UnitsAdmin } from './UnitsAdmin'

const UNITS: UnitOut[] = [
  { id: 'u-204', kind: 'guest_room', code: '204', name: 'Room 204', floor: 2, roomType: 'KNGN',
    active: true, source: 'manual', externalId: null, notes: null, createdAt: '2026-09-01T00:00:00Z' },
]

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve(importResponse?: { status: number; body: unknown }) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/import')) return json(importResponse?.body ?? { created: 3, updated: 0, errors: [] }, importResponse?.status ?? 200)
    if (init?.method === 'POST') return json({ ...UNITS[0], id: 'u-new', code: '205' }, 201)
    if (init?.method === 'PATCH') return json({ ...UNITS[0], active: false })
    return json(UNITS)
  })
}

function mount() {
  return renderWithProviders(
    <ToastProvider>
      <SessionProvider>
        <UnitsAdmin />
      </SessionProvider>
    </ToastProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

describe('UnitsAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists units for the selected kind and asks the server for that kind', async () => {
    serve()
    mount()
    expect(await screen.findByText('Room 204')).toBeInTheDocument()
    expect(String(vi.mocked(fetch).mock.calls[0]![0])).toContain('maintainable-units?kind=guest_room')
    await userEvent.click(screen.getByRole('tab', { name: 'Equipment' }))
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes('kind=equipment'))).toBe(true))
  })

  it('creates a unit from the panel', async () => {
    serve()
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New unit' }))
    await userEvent.type(screen.getByLabelText('Code'), '205')
    await userEvent.type(screen.getByLabelText('Name'), 'Room 205')
    await userEvent.type(screen.getByLabelText('Floor'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')!
      expect(JSON.parse(String(post[1]!.body))).toEqual({
        kind: 'guest_room', code: '205', name: 'Room 205', floor: 2, roomType: null,
        externalId: null, notes: null,
      })
    })
  })

  it('shows the per-row report when an import is rejected, and success counts otherwise', async () => {
    serve({
      status: 422,
      body: { error: { code: 'IMPORT_REJECTED', message: 'Import rejected', details: {
        created: 0, updated: 0,
        errors: [{ line: 3, field: 'kind', message: 'must be one of guest_room, common_area, equipment' }],
      } } },
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Import CSV' }))
    const dialog = screen.getByRole('dialog')
    const file = new File(['code,kind,name,floor,room_type,external_id\n'], 'units.csv', { type: 'text/csv' })
    await userEvent.upload(within(dialog).getByLabelText('CSV file'), file)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }))
    expect(await within(dialog).findByText('Line 3')).toBeInTheDocument()
    expect(within(dialog).getByText(/must be one of/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Nothing was imported/)).toBeInTheDocument()
  })
})
