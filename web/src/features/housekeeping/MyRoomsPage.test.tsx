import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { HkAssignmentOut, HkRoomOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { MyRoomsPage } from './MyRoomsPage'

function assignment(over: Partial<HkAssignmentOut>): HkAssignmentOut {
  return {
    id: 'a-1', roomId: 'r-1', housekeeperUserId: 'u-hana', housekeeperName: 'Hana Keeper',
    shiftDate: '2026-09-10', sequence: 1, type: 'departure', status: 'assigned', startedAt: null,
    completedAt: null, inspectedByName: null, inspectedAt: null, inspectionNote: null,
    failCount: 0, ...over,
  }
}

function room(code: string, a: HkAssignmentOut, over: Partial<HkRoomOut> = {}): HkRoomOut {
  return {
    id: a.roomId, unitId: `u-${code}`, code, floor: 2, roomType: 'KNGN', hkStatus: 'dirty',
    serviceType: a.type, rush: false, occupancy: 'vacant', guestName: null, departureDate: null,
    statusChangedAt: '2026-09-10T08:00:00Z', lastCleanedAt: null, lastInspectedAt: null,
    notes: null, assignment: a, ...over,
  }
}

const MINE: HkRoomOut[] = [
  room('204', assignment({ id: 'a-rush', roomId: 'r-204' }), { rush: true }),
  room('205', assignment({ id: 'a-2', roomId: 'r-205', status: 'in_progress', sequence: 2 }),
       { hkStatus: 'in_progress' }),
  room('206', assignment({ id: 'a-3', roomId: 'r-206', sequence: 3, failCount: 1,
                           inspectionNote: 'Hair in the bathroom sink.' })),
  room('207', assignment({ id: 'a-4', roomId: 'r-207', status: 'passed', sequence: 4 }),
       { hkStatus: 'inspected' }),
]

const posts: string[] = []

describe('MyRoomsPage', () => {
  beforeEach(() => {
    posts.length = 0
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') posts.push(String(input))
      return Promise.resolve(new Response(JSON.stringify(MINE), { status: 200 }))
    }))
    renderWithProviders(
      <SessionProvider>
        <Routes>
          <Route path="/app/my-rooms" element={<MyRoomsPage />} />
        </Routes>
      </SessionProvider>,
      { session: sessionFixture({ role: 'dept_staff', departmentType: 'housekeeping' }), route: '/app/my-rooms' },
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows progress and pins rush at the top', async () => {
    expect(await screen.findByText('1 of 4 done')).toBeInTheDocument()
    const rows = screen.getAllByRole('button', { name: /^Open room / })
    expect(rows[0]).toHaveAccessibleName('Open room 204')
    expect(screen.getByText('Rush')).toBeInTheDocument()
  })

  it('walks the one big button from Start to Mark ready', async () => {
    const user = userEvent.setup()
    const starts = await screen.findAllByRole('button', { name: 'Start' })
    await user.click(starts[0]!)
    expect(posts.some((p) => p.endsWith('/assignments/a-rush/start'))).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Mark ready' }))
    expect(posts.some((p) => p.endsWith('/assignments/a-2/complete'))).toBe(true)
  })

  it('opens a room full screen with the failed-back note', async () => {
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Open room 206' }))
    expect(screen.getByText(/Hair in the bathroom sink\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to my rooms' })).toBeInTheDocument()
  })

  it('shows the server error inline when starting a room fails', async () => {
    vi.mocked(fetch).mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({
          error: { code: 'INVALID_TRANSITION', message: 'Only an assigned, dirty room can be started' },
        }), { status: 409 }))
      }
      return Promise.resolve(new Response(JSON.stringify(MINE), { status: 200 }))
    })
    const user = userEvent.setup()
    const starts = await screen.findAllByRole('button', { name: 'Start' })
    await user.click(starts[0]!)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only an assigned, dirty room can be started',
    )
  })
})
