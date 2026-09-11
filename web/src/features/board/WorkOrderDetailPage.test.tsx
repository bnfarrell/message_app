import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser, aWorkOrderDetail } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { WorkOrderDetailPage } from './WorkOrderDetailPage'

function serve(detail: unknown) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer' })]
        : detail
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/work-orders/:id" element={<WorkOrderDetailPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'supervisor' }), route: '/app/work-orders/w-204' },
  )
}

describe('WorkOrderDetailPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the id, title, room, status and priority', async () => {
    serve(aWorkOrderDetail({ status: 'complete' }))
    mount()
    expect(await screen.findByText('#w-204')).toBeInTheDocument()
    expect(screen.getByText('AC not cooling')).toBeInTheDocument()
    expect(screen.getByText('412')).toBeInTheDocument()
    expect(screen.getByText('Complete')).toBeInTheDocument()
    expect(screen.getByText('urgent')).toBeInTheDocument()
  })

  it('resolves the department and assignee names', async () => {
    serve(aWorkOrderDetail({ assignedUserId: 'u-eli' }))
    mount()
    expect(await screen.findByText('Engineering')).toBeInTheDocument()
    expect(screen.getByText('Eli Engineer')).toBeInTheDocument()
  })

  it('shows the elapsed time when complete', async () => {
    serve(
      aWorkOrderDetail({
        createdAt: '2026-09-10T18:42:00Z',
        completedAt: '2026-09-10T18:56:00Z',
        status: 'complete',
      }),
    )
    mount()
    expect(await screen.findByText(/14m/)).toBeInTheDocument()
  })

  it('links back to the source conversation', async () => {
    serve(aWorkOrderDetail({ sourceConversationId: 'c-1' }))
    mount()
    expect(await screen.findByRole('link', { name: /open conversation/i })).toHaveAttribute(
      'href',
      '/app/inbox/c-1',
    )
  })

  it('says Not yet when the guest has not been told', async () => {
    serve(aWorkOrderDetail({ guestNotifiedAt: null }))
    mount()
    expect(await screen.findByText('Not yet')).toBeInTheDocument()
  })

  it('renders the timeline newest first', async () => {
    serve(
      aWorkOrderDetail({
        events: [
          { id: 'e1', type: 'created', userId: 'u-ava', userName: 'Ava', fromValue: null, toValue: null, comment: null, createdAt: '2026-09-10T18:42:00Z' },
          { id: 'e2', type: 'status_changed', userId: 'u-eli', userName: 'Eli', fromValue: 'open', toValue: 'in_progress', comment: null, createdAt: '2026-09-10T18:47:00Z' },
        ],
      }),
    )
    mount()
    const items = await screen.findAllByRole('listitem')
    expect(items[0]).toHaveTextContent('status changed')
    expect(items[1]).toHaveTextContent('created')
  })

  it('shows a transition comment in the timeline', async () => {
    serve(
      aWorkOrderDetail({
        events: [
          { id: 'e1', type: 'status_changed', userId: 'u-eli', userName: 'Eli', fromValue: 'in_progress', toValue: 'blocked', comment: 'Waiting on a part', createdAt: '2026-09-10T18:50:00Z' },
        ],
      }),
    )
    mount()
    expect(await screen.findByText('Waiting on a part')).toBeInTheDocument()
  })
})
