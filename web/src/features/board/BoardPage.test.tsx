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
  aWorkOrder({ id: 'w-5', status: 'verified', title: 'Pool pump serviced', locationRef: 'POOL', priority: 'normal' }),
  aWorkOrder({ id: 'w-6', status: 'cancelled', title: 'Duplicate ice request', locationRef: '3F', priority: 'normal' }),
]

// The real server withholds verified and cancelled unless includeClosed is set, so the mock
// must too — otherwise the reveal toggle looks like it works while fetching nothing new.
function serve(orders = ORDERS) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer' })]
        : url.includes('includeClosed=true')
          ? orders
          : orders.filter((w) => w.status !== 'verified' && w.status !== 'cancelled')
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

  it('lets only one filter tab be selected at a time', async () => {
    // Reported from the running app: "two tabs can be selected at same time." The mockup draws
    // five `.tab`s with exactly one `.on`, so picking a tab must clear the others.
    // Changing mine/dept changes the query key, so the board flips through its pending spinner
    // and re-mounts the tabs: every tab has to be looked up again after a click.
    mount()
    await userEvent.click(await screen.findByRole('tab', { name: 'Mine' }))
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Mine' })).toHaveAttribute('aria-selected', 'true'),
    )

    await userEvent.click(await screen.findByRole('tab', { name: 'Engineering' }))
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Engineering' })).toHaveAttribute(
        'aria-selected',
        'true',
      ),
    )
    expect(screen.getByRole('tab', { name: 'Mine' })).toHaveAttribute('aria-selected', 'false')

    await waitFor(() => {
      const last = vi
        .mocked(fetch)
        .mock.calls.map(([u]) => String(u))
        .filter((u) => u.includes('/work-orders'))
        .at(-1)!
      expect(last).toContain('dept=dept-eng')
      expect(last).not.toContain('mine=true')
    })
  })

  it('lights exactly one tab even when a stale URL still carries two filters', async () => {
    mount('/app/board?mine=1&dept=dept-eng&urgent=1')
    await screen.findByRole('tab', { name: 'Engineering' })
    const lit = screen.getAllByRole('tab').filter((t) => t.getAttribute('aria-selected') === 'true')
    expect(lit).toHaveLength(1)
  })

  it('links each card to its detail screen', async () => {
    mount()
    expect(await screen.findByRole('link', { name: /Faucet dripping/ })).toHaveAttribute(
      'href',
      '/app/work-orders/w-1',
    )
  })

  it('hides verified and cancelled work until the footer control reveals them', async () => {
    mount()
    await screen.findByText('Faucet dripping')
    expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('includeClosed'))).toBe(
      false,
    )
    expect(screen.queryByText('Pool pump serviced')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Verified/ })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /show closed/i }))

    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('includeClosed=true')),
      ).toBe(true),
    )
    expect(await screen.findByText('Pool pump serviced')).toBeInTheDocument()
    expect(screen.getByText('Duplicate ice request')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Verified/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Cancelled/ })).toBeInTheDocument()
    // A real count of what actually came back, not the mockup's illustrative "46 this week".
    expect(screen.getByText(/Showing/)).toHaveTextContent('Showing 2 verified and cancelled')
    // Terminal work must not be counted as active, nor absorbed into the five open columns.
    expect(screen.getByText(/4 active · 2 urgent/)).toBeInTheDocument()
    const complete = screen.getByRole('heading', { name: /Complete/ }).parentElement!
    expect(complete).not.toHaveTextContent('Pool pump serviced')

    await userEvent.click(screen.getByRole('button', { name: /hide them/i }))
    await waitFor(() => expect(screen.queryByText('Pool pump serviced')).not.toBeInTheDocument())
  })

  it('round-trips the reveal through the URL, so a revealed board is linkable', async () => {
    mount('/app/board?closed=1')
    expect(await screen.findByText('Pool pump serviced')).toBeInTheDocument()
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('includeClosed=true')),
      ).toBe(true),
    )
  })

  it('groups the revealed closed work by outcome in the list view too', async () => {
    mount('/app/board?closed=1&view=list')
    const verified = await screen.findByRole('heading', { name: /Verified/ })
    expect(verified.parentElement).toHaveTextContent('Pool pump serviced')
    expect(verified.parentElement).not.toHaveTextContent('Faucet dripping')
    expect(screen.getByRole('heading', { name: /Cancelled/ }).parentElement).toHaveTextContent(
      'Duplicate ice request',
    )
  })

  it('keeps the reveal when All clears the filters', async () => {
    mount('/app/board?closed=1&urgent=1')
    await userEvent.click(await screen.findByRole('tab', { name: /All/ }))
    expect(await screen.findByText('Pool pump serviced')).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    serve([])
    mount()
    expect(await screen.findByText(/nothing on the board/i)).toBeInTheDocument()
  })
})
