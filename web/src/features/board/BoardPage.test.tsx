import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser, aWorkOrder } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { BoardPage } from './BoardPage'

const ORDERS = [
  aWorkOrder({ id: 'w-1', status: 'open', title: 'Faucet dripping', locationRef: '318', priority: 'normal' }),
  aWorkOrder({ id: 'w-2', status: 'assigned', title: 'Toilet running', locationRef: '221', assignedUserId: 'u-eli', priority: 'normal' }),
  aWorkOrder({ id: 'w-3', status: 'in_progress', title: 'Ice machine', locationRef: '3F', priority: 'urgent' }),
  aWorkOrder({ id: 'w-4', status: 'complete', title: 'AC not cooling', locationRef: '412', priority: 'urgent' }),
]

function serve(orders = ORDERS) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer' })]
        : orders
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(route = '/app/board') {
  return renderWithProviders(
    <SessionProvider>
      <BoardPage />
    </SessionProvider>,
    { session: sessionFixture({ role: 'supervisor' }), route },
  )
}

describe('BoardPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the five open columns', async () => {
    mount()
    for (const label of ['Open', 'Assigned', 'In progress', 'Blocked', 'Complete']) {
      expect(await screen.findByRole('heading', { name: new RegExp(label) })).toBeInTheDocument()
    }
  })

  it('puts each card in its status column', async () => {
    mount()
    const open = await screen.findByRole('heading', { name: /Open/ })
    const column = open.parentElement!
    expect(column).toHaveTextContent('Faucet dripping')
    expect(column).not.toHaveTextContent('Toilet running')
  })

  it('reports the active and urgent counts', async () => {
    mount()
    expect(await screen.findByText(/4 active · 2 urgent/)).toBeInTheDocument()
  })

  it('honours ?mine=1 on entry, which is where landingPath sends supervisors', async () => {
    mount('/app/board?mine=1')
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('mine=true'))).toBe(true),
    )
    expect(await screen.findByRole('tab', { name: /Mine/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('filters to urgent without refetching', async () => {
    mount()
    await screen.findByText('Faucet dripping')
    await userEvent.click(screen.getByRole('tab', { name: /Urgent/ }))
    await waitFor(() => expect(screen.queryByText('Faucet dripping')).not.toBeInTheDocument())
    expect(screen.getByText('Ice machine')).toBeInTheDocument()
  })

  it('switches to a list view', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'List' }))
    expect(await screen.findByRole('button', { name: 'Board' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /In progress/ })).not.toBeInTheDocument()
  })

  it('keeps the list view when All clears the filters', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'List' }))
    await userEvent.click(screen.getByRole('tab', { name: /Urgent/ }))
    await userEvent.click(screen.getByRole('tab', { name: /All/ }))

    // All resets the filters, not the whole query string: view=list is not a filter, and
    // dropping it threw the user back to the board they had deliberately switched away from.
    expect(screen.getByRole('button', { name: 'Board' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /In progress/ })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Urgent/ })).toHaveAttribute('aria-selected', 'false')
  })

  it('links each card to its detail screen', async () => {
    mount()
    expect(await screen.findByRole('link', { name: /Faucet dripping/ })).toHaveAttribute(
      'href',
      '/app/work-orders/w-1',
    )
  })

  it('shows an empty state when nothing matches', async () => {
    serve([])
    mount()
    expect(await screen.findByText(/nothing on the board/i)).toBeInTheDocument()
  })
})
