import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { HkInspectionRowOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { RoomInspectionPage } from './RoomInspectionPage'

const QUEUE: HkInspectionRowOut[] = [{
  room: {
    id: 'r-204', unitId: 'u-204', code: '204', floor: 2, roomType: 'KNGN', hkStatus: 'clean',
    serviceType: 'departure', rush: false, occupancy: 'vacant', guestName: null,
    departureDate: null, statusChangedAt: '2026-09-10T13:00:00Z', lastCleanedAt: null,
    lastInspectedAt: null, notes: null,
    assignment: {
      id: 'a-204', roomId: 'r-204', housekeeperUserId: 'u-hana', housekeeperName: 'Hana Keeper',
      shiftDate: '2026-09-10', sequence: 1, type: 'departure', status: 'done',
      startedAt: '2026-09-10T12:30:00Z', completedAt: '2026-09-10T13:00:00Z',
      inspectedByName: null, inspectedAt: null, inspectionNote: null, failCount: 0,
    },
  },
  photos: [{ id: 'p-1', contentType: 'image/png', byteSize: 10, url: '/api/p/prop-a/x.png',
             createdAt: '2026-09-10T12:50:00Z' }],
}]

const posts: { url: string; body: unknown }[] = []

describe('RoomInspectionPage', () => {
  beforeEach(() => {
    posts.length = 0
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') {
        posts.push({ url: String(input), body: JSON.parse(String(init!.body)) })
        return Promise.resolve(new Response('{}', { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify(QUEUE), { status: 200 }))
    }))
    renderWithProviders(
      <SessionProvider>
        <Routes>
          <Route path="/app/room-inspection" element={<RoomInspectionPage />} />
        </Routes>
      </SessionProvider>,
      { session: sessionFixture({ role: 'supervisor' }), route: '/app/room-inspection' },
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists who cleaned each room, with their photos', async () => {
    expect(await screen.findByText('204')).toBeInTheDocument()
    expect(screen.getByText(/Hana Keeper/)).toBeInTheDocument()
    expect(screen.getAllByRole('img')).toHaveLength(1)
  })

  it('passes a room', async () => {
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Pass room 204' }))
    expect(posts).toEqual([{ url: '/api/p/prop-a/housekeeping/assignments/a-204/inspect',
                             body: { result: 'pass', note: null } }])
  })

  it('will not fail a room without a note', async () => {
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Fail room 204' }))
    const confirm = screen.getByRole('button', { name: 'Fail room' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('What needs fixing?'), '   ')
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('What needs fixing?'), 'Streaky mirror.')
    await user.click(confirm)
    expect(posts[0]!.body).toEqual({ result: 'fail', note: 'Streaky mirror.' })
  })
})
