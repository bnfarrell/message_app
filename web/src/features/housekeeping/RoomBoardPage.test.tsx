import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { HkBoardOut, HkRoomOut, Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { RoomBoardPage } from './RoomBoardPage'

function room(over: Partial<HkRoomOut>): HkRoomOut {
  return {
    id: 'r-101', unitId: 'u-101', code: '101', floor: 1, roomType: 'KNGN', hkStatus: 'dirty',
    serviceType: 'stayover', rush: false, occupancy: 'stayover', guestName: 'Sarah Chen',
    departureDate: '2026-09-12', statusChangedAt: '2026-09-10T08:00:00Z', lastCleanedAt: null,
    lastInspectedAt: null, notes: null, assignment: null, ...over,
  }
}

const BOARD: HkBoardOut = {
  rooms: [
    room({}),
    room({ id: 'r-102', code: '102', hkStatus: 'inspected', occupancy: 'vacant', guestName: null }),
    room({ id: 'r-103', code: '103', rush: true }),
    room({ id: 'r-PH', code: 'PH', floor: null }),
  ],
  summary: { dirty: 3, inProgress: 0, awaitingInspection: 0, inspected: 1, outOfOrder: 0 },
  housekeepers: [{ userId: 'u-hana', name: 'Hana Keeper', assigned: 0, done: 0 }],
}

const calls: { url: string; method: string; body: unknown }[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = url.endsWith('/housekeeping/board') ? BOARD : method === 'POST' ? [] : {}
    return Promise.resolve(new Response(JSON.stringify(body), { status: method === 'POST' ? 201 : 200 }))
  })
}

function mount(role: Role) {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/housekeeping" element={<RoomBoardPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role }), route: '/app/housekeeping' },
  )
}

describe('RoomBoardPage', () => {
  beforeEach(() => {
    calls.length = 0
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows the summary and groups rooms by floor with floorless rooms last', async () => {
    mount('supervisor')
    expect(await screen.findByRole('heading', { name: 'Floor 1' })).toBeInTheDocument()
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Floor 1', 'No floor'])
    expect(screen.getByTestId('summary-dirty')).toHaveTextContent('3')
  })

  it('puts rush rooms first on their floor', async () => {
    mount('supervisor')
    await screen.findByRole('heading', { name: 'Floor 1' })
    const tiles = screen.getAllByRole('button', { name: /^Room / }).map((b) => b.getAttribute('aria-label'))
    expect(tiles.slice(0, 3)).toEqual(['Room 103, Dirty', 'Room 101, Dirty', 'Room 102, Inspected'])
  })

  it('assigns every selected room in one request', async () => {
    const user = userEvent.setup()
    mount('supervisor')
    await user.click(await screen.findByRole('checkbox', { name: 'Select room 101' }))
    await user.click(screen.getByRole('checkbox', { name: 'Select room PH' }))
    await user.selectOptions(screen.getByLabelText('Assign to'), 'u-hana')
    await user.click(screen.getByRole('button', { name: 'Assign' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/housekeeping/assignments'))
    expect(post?.body).toEqual({ roomIds: ['r-101', 'r-PH'], housekeeperUserId: 'u-hana' })
  })

  it('gives front desk Mark dirty and Rush but not Assign', async () => {
    const user = userEvent.setup()
    mount('agent')
    await user.click(await screen.findByRole('checkbox', { name: 'Select room 102' }))
    expect(screen.queryByLabelText('Assign to')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mark dirty' }))
    expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/rooms/r-102/mark-dirty'))).toBe(true)
  })

  it('filters to unassigned rooms of one status', async () => {
    const user = userEvent.setup()
    mount('supervisor')
    await screen.findByRole('heading', { name: 'Floor 1' })
    await user.selectOptions(screen.getByLabelText('Status'), 'inspected')
    const tiles = screen.getAllByRole('button', { name: /^Room / })
    expect(tiles).toHaveLength(1)
    expect(within(tiles[0]!.closest('li')!).getByText('102')).toBeInTheDocument()
  })
})
