import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { ComplianceOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { CompliancePage } from './CompliancePage'

const REPORT: ComplianceOut = {
  templates: [
    { id: 't-1', name: 'Guest Room Quarterly', mode: 'sweep', unitKind: 'guest_room',
      cycles: [
        { ordinal: 2, startsOn: '2026-04-01', endsOn: '2026-06-30', status: 'closed', passed: 110, missed: 10, total: 120, onTimePct: 91.7 },
        { ordinal: 3, startsOn: '2026-07-01', endsOn: '2026-09-30', status: 'open', passed: 40, missed: 0, total: 120, onTimePct: 33.3 },
      ],
      runs: null, inspectionPassRate: 95.2 },
    { id: 't-2', name: 'Boiler inspection', mode: 'scheduled', unitKind: null, cycles: [],
      runs: { due: 2, passed: 1, failed: 0, overdue: 1 }, inspectionPassRate: 100 },
  ],
}

function mount() {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(REPORT), { status: 200 }))
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/pm/compliance" element={<CompliancePage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'manager' }), route: '/app/pm/compliance' },
  )
}

describe('CompliancePage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a cycle table for sweeps and due/overdue for schedules', async () => {
    mount()
    expect(await screen.findByText('Guest Room Quarterly')).toBeInTheDocument()
    expect(screen.getByText('2nd Cycle')).toBeInTheDocument()
    expect(screen.getByText('91.7%')).toBeInTheDocument()
    expect(screen.getByText('Inspection pass rate 95.2%')).toBeInTheDocument()
    expect(screen.getByText('Boiler inspection')).toBeInTheDocument()
    expect(screen.getByText('1 overdue')).toBeInTheDocument()
  })

  it('asks the server for the chosen window', async () => {
    mount()
    await screen.findByText('Guest Room Quarterly')
    const url = String(vi.mocked(fetch).mock.calls[0]![0])
    expect(url).toMatch(/pm\/compliance\?from=\d{4}-01-01&to=\d{4}-\d{2}-\d{2}$/)
  })
})
