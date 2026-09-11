import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser, aWorkOrderDetail } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { WorkOrderDetailPage } from './WorkOrderDetailPage'

// A PATCH answers with the updated detail and every later GET sees it, the way the real route
// does — the client only learns a comment landed by refetching the detail.
function serve(detail: unknown, afterPatch?: unknown) {
  let current = detail
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PATCH') current = afterPatch ?? detail
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer' })]
        : current
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

  // G1's new event type. The generic "type → toValue" phrasing every other event uses would
  // read as "photo attached → after"; the mockup's own wording is "after photo attached".
  it('phrases a photo_attached event naturally, matching the mockup', async () => {
    serve(
      aWorkOrderDetail({
        events: [
          { id: 'e1', type: 'photo_attached', userId: 'u-eli', userName: 'Eli', fromValue: null, toValue: 'after', comment: null, createdAt: '2026-09-10T18:56:00Z' },
        ],
      }),
    )
    mount()
    expect(await screen.findByText('after photo attached')).toBeInTheDocument()
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

  it('posts a standalone comment and shows it in the timeline', async () => {
    serve(
      aWorkOrderDetail({ events: [] }),
      aWorkOrderDetail({
        events: [
          { id: 'e9', type: 'commented', userId: 'u-ava', userName: 'Ava', fromValue: null, toValue: null, comment: 'Parts ordered, ETA Thursday', createdAt: '2026-09-10T19:10:00Z' },
        ],
      }),
    )
    mount()
    const box = await screen.findByLabelText('Comment')
    await userEvent.type(box, 'Parts ordered, ETA Thursday')
    await userEvent.click(screen.getByRole('button', { name: 'Comment' }))

    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    // Comment only: no status rides along, which is what made the server branch reachable.
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ comment: 'Parts ordered, ETA Thursday' })

    await waitFor(() => expect(box).toHaveValue(''))
    expect(await screen.findByRole('listitem')).toHaveTextContent('Parts ordered, ETA Thursday')
  })

  it('will not post an empty or whitespace-only comment', async () => {
    serve(aWorkOrderDetail())
    mount()
    await screen.findByLabelText('Comment')
    expect(screen.getByRole('button', { name: 'Comment' })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Comment'), '   ')
    expect(screen.getByRole('button', { name: 'Comment' })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Comment'), 'x')
    expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled()
  })
})
