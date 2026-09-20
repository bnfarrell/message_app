import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import type { SweepOut, SweepUnitOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { SweepPage } from './SweepPage'

function unit(over: Partial<SweepUnitOut>): SweepUnitOut {
  return {
    id: 'u-204', code: '204', name: 'Room 204', floor: 2, roomType: 'KNGN',
    lastPassedAt: null, lastPassedByName: null, passedThisCycle: false, currentRun: null,
    ...over,
  }
}

const SWEEP: SweepOut = {
  template: { id: 't-1', name: 'Guest Room Quarterly', cadence: 'quarterly' },
  cycle: { id: 'cy-3', ordinal: 3, startsOn: '2026-07-01', endsOn: '2026-09-30', daysLeft: 20 },
  counts: { remaining: 3, completed: 1, total: 4 },
  units: [
    unit({ id: 'u-101', code: '101', name: 'Room 101', floor: 1 }),
    unit({ id: 'u-204', code: '204', passedThisCycle: true, lastPassedAt: '2026-08-02T14:00:00Z',
           lastPassedByName: 'Eli Engineer' }),
    unit({ id: 'u-205', code: '205', name: 'Room 205',
           currentRun: { id: 'run-205', status: 'in_progress', startedByUserId: 'u-noah',
                         startedByName: 'Noah Fix' } }),
    unit({ id: 'u-206', code: '206', name: 'Room 206',
           currentRun: { id: 'run-206', status: 'completed', startedByUserId: 'u-eli',
                         startedByName: 'Eli Engineer' } }),
  ],
}

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}

function serve(sweep: SweepOut, onStart?: () => unknown) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/pm/runs') && init?.method === 'POST') {
      const body = onStart?.() ?? { id: 'run-new', status: 'in_progress' }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 201 }))
    }
    if (url.includes('/pm/sweep')) {
      return Promise.resolve(new Response(JSON.stringify(sweep), { status: 200 }))
    }
    return Promise.resolve(new Response('[]', { status: 200 }))
  })
}

function mount(role: 'agent' | 'dept_staff' | 'admin' = 'dept_staff', route = '/app/pm') {
  return renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <Routes>
          <Route path="/app/pm" element={<SweepPage />} />
          <Route path="/app/pm/runs/:id" element={<div>run page</div>} />
        </Routes>
        <LocationDisplay />
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role }), route },
  )
}

describe('SweepPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the three tiles from the payload', async () => {
    serve(SWEEP)
    mount()
    expect(await screen.findByText('3')).toBeInTheDocument()
    // { selector: 'span' } scopes to the tile label — the Show filter below also has an
    // option reading "Remaining"/"Completed", so an unscoped query matches both.
    expect(screen.getByText('Remaining', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('3rd Cycle')).toBeInTheDocument()
    expect(screen.getByText('Jul 01 – Sep 30')).toBeInTheDocument()
    expect(screen.getByText('20 days')).toBeInTheDocument()
    expect(screen.getByText('Completed', { selector: 'span' })).toBeInTheDocument()
  })

  it('shows one action per row from the unit state', async () => {
    serve(SWEEP)
    mount()
    expect(await screen.findByRole('button', { name: 'Start' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Continue/ })).toHaveTextContent('Noah Fix')
    expect(screen.getByRole('button', { name: 'Awaiting inspection' })).toBeDisabled()
  })

  it('starts a run and lands on it', async () => {
    serve(SWEEP)
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Start' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/pm/runs/run-new'))
    const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(String(post[1]!.body))).toEqual({ templateId: 't-1', unitId: 'u-101' })
  })

  it('follows a 409 to the run somebody else already started', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/pm/runs') && init?.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({
          error: { code: 'CONFLICT', message: 'Already running', details: { runId: 'run-other' } },
        }), { status: 409 }))
      }
      if (url.includes('/pm/sweep')) return Promise.resolve(new Response(JSON.stringify(SWEEP), { status: 200 }))
      return Promise.resolve(new Response('[]', { status: 200 }))
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Start' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/pm/runs/run-other'))
  })

  it('hides Start from a role without perform_pm', async () => {
    serve(SWEEP)
    mount('agent')
    expect(await screen.findByText('Room 101')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument()
  })

  it('names the missing template when a kind is unconfigured', async () => {
    serve({ template: null, cycle: null, counts: { remaining: 0, completed: 0, total: 0 }, units: [] })
    mount('admin', '/app/pm?kind=equipment')
    expect(await screen.findByText(/No sweep template for Equipment/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /PM templates/ })).toHaveAttribute('href', '/app/admin/pm-templates')
  })

  it('puts the kind, filter and sort in the URL', async () => {
    serve(SWEEP)
    mount()
    await screen.findByText('Room 101')
    await userEvent.click(screen.getByRole('tab', { name: 'Equipment' }))
    expect(screen.getByTestId('location')).toHaveTextContent('kind=equipment')
    await userEvent.selectOptions(screen.getByLabelText('Show'), 'remaining')
    expect(screen.getByTestId('location')).toHaveTextContent('status=remaining')
  })
})
