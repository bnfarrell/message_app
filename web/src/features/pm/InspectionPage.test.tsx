import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { InspectionRowOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { InspectionPage } from './InspectionPage'

const AVAILABLE: InspectionRowOut[] = [
  { runId: 'run-1', unitId: 'u-204', unitCode: '204', unitName: 'Room 204', unitKind: 'guest_room',
    templateName: 'Guest Room Quarterly', completedByName: 'Eli Engineer',
    completedAt: '2026-09-10T12:40:00Z', daysSinceLastPm: 94, status: 'completed',
    inspectedByName: null, inspectedAt: null },
]
const INSPECTED: InspectionRowOut[] = [
  { ...AVAILABLE[0]!, runId: 'run-0', unitCode: '101', unitName: 'Room 101', status: 'passed',
    inspectedByName: 'Sam Super', inspectedAt: '2026-09-09T15:00:00Z' },
  { ...AVAILABLE[0]!, runId: 'run-x', unitCode: '102', unitName: 'Room 102', status: 'failed',
    inspectedByName: 'Sam Super', inspectedAt: '2026-09-09T16:00:00Z' },
]

function serve(available: InspectionRowOut[], inspected: InspectionRowOut[]) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('status=inspected') ? inspected : available
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/inspection" element={<InspectionPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'supervisor' }), route: '/app/inspection' },
  )
}

describe('InspectionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows both queue counts and the available rows by default', async () => {
    serve(AVAILABLE, INSPECTED)
    mount()
    expect(await screen.findByRole('tab', { name: 'Available for Inspection 1' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Inspected 2' })).toBeInTheDocument()
    const row = screen.getByRole('link', { name: /Room 204/ })
    expect(row).toHaveAttribute('href', '/app/pm/runs/run-1')
    expect(row).toHaveTextContent('94 days since last PM')
  })

  it('switches to the inspected list with results', async () => {
    serve(AVAILABLE, INSPECTED)
    mount()
    await userEvent.click(await screen.findByRole('tab', { name: 'Inspected 2' }))
    expect(await screen.findByText('Passed')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getAllByText(/Sam Super/)).toHaveLength(2)
  })

  it('has an empty state naming the kind', async () => {
    serve([], [])
    mount()
    await userEvent.click(await screen.findByRole('tab', { name: 'Guest Rooms' }))
    expect(await screen.findByText('No guest rooms PMs are pending for inspection')).toBeInTheDocument()
  })

  it('marks a failed count as failed rather than leaving it looking like it is still loading', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('status=inspected')) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: 'SERVER_ERROR', message: 'boom' } }), {
            status: 500,
          }),
        )
      }
      return Promise.resolve(new Response(JSON.stringify(AVAILABLE), { status: 200 }))
    })
    mount()
    expect(await screen.findByRole('tab', { name: 'Available for Inspection 1' })).toBeInTheDocument()
    expect(await screen.findByTitle('Could not load this count')).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Inspected …' })).not.toBeInTheDocument()
  })
})
