import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { AnalyticsPage } from './AnalyticsPage'

const OVERVIEW = {
  since: '2026-09-04',
  until: '2026-09-10',
  conversations: 214,
  inboundMessages: 512,
  outboundMessages: 498,
  firstResponseP50Seconds: 160,
  firstResponseP90Seconds: 665,
  slaBreaches: 9,
  slaBreachRate: 0.042,
  workOrdersCreated: 70,
  workOrdersClosed: 61,
  workOrdersFromConversations: 9,
  meanTimeToResolveSeconds: 2280,
  inboundByHour: [
    { hour: 0, count: 2 },
    { hour: 18, count: 31 },
  ],
  inboundByDay: [{ day: '2026-09-10', count: 40 }],
  firstResponseDistribution: [
    { label: '< 2 min', count: 88, share: 0.41 },
    { label: '15–30', count: 19, share: 0.09 },
  ],
  workOrdersByDepartment: [
    { departmentId: 'dept-eng', departmentName: 'Engineering', closed: 34, meanTimeToResolveSeconds: 2820 },
  ],
}

const AGENTS = [
  {
    userId: 'u-ava',
    name: 'Ava',
    conversationsHandled: 82,
    messagesSent: 190,
    firstResponseP50Seconds: 110,
    firstResponseP90Seconds: 400,
    slaBreaches: 1,
    quickReplyShare: 0.61,
    workOrdersCreated: 14,
  },
]

function serve(overview: unknown = OVERVIEW, agents: unknown = AGENTS) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) =>
    Promise.resolve(
      new Response(JSON.stringify(String(input).includes('/agents') ? agents : overview), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

function mount(role: 'manager' | 'supervisor' = 'manager') {
  return renderWithProviders(
    <SessionProvider>
      <AnalyticsPage />
    </SessionProvider>,
    { session: sessionFixture({ role }), route: '/app/analytics' },
  )
}

describe('AnalyticsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the four KPI cards with the server numbers', async () => {
    mount()
    expect(await screen.findByText('214')).toBeInTheDocument()
    expect(screen.getByText('2m 40s')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
    expect(screen.getByText('61')).toBeInTheDocument()
  })

  it('shows the breach rate as a percentage', async () => {
    mount()
    expect(await screen.findByText(/4\.2% of conversations/)).toBeInTheDocument()
  })

  it('renders an em dash, not 0s, when there is no first-response data', async () => {
    serve({ ...OVERVIEW, firstResponseP50Seconds: null, firstResponseP90Seconds: null })
    mount()
    await screen.findByText('214')
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText('0s')).not.toBeInTheDocument()
  })

  it('defaults to the 7-day range', async () => {
    mount()
    await screen.findByText('214')
    expect(screen.getByRole('tab', { name: '7 days' })).toHaveAttribute('aria-selected', 'true')
  })

  it('refetches for a new range', async () => {
    mount()
    await screen.findByText('214')
    await userEvent.click(screen.getByRole('tab', { name: 'Today' }))
    await waitFor(() => {
      const ranges = vi.mocked(fetch).mock.calls.map(([u]) => String(u))
      const today = ranges.filter((u) => u.includes('overview'))
      expect(new Set(today).size).toBeGreaterThan(1)
    })
  })

  it('renders the agents table', async () => {
    mount()
    expect(await screen.findByText('Ava')).toBeInTheDocument()
    expect(screen.getByText('82')).toBeInTheDocument()
    expect(screen.getByText('61%')).toBeInTheDocument()
  })

  it('renders an empty agents table without crashing', async () => {
    serve(OVERVIEW, [])
    mount()
    expect(await screen.findByText(/no agent activity/i)).toBeInTheDocument()
  })

  it('shows Export to a manager', async () => {
    mount('manager')
    expect(await screen.findByRole('button', { name: 'Export' })).toBeInTheDocument()
  })

  it('hides Export from a supervisor, who lacks the capability', async () => {
    mount('supervisor')
    await screen.findByText('214')
    expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument()
  })

  it('marks the over-SLA reply bucket in red', async () => {
    mount()
    await screen.findByText('214')
    expect(screen.getByText('9%').className).toContain('dangerText')
  })

  it('shows the department breakdown', async () => {
    mount()
    expect(await screen.findByText('Engineering')).toBeInTheDocument()
    // Defect in the brief's fixture: departmentBucket.meanTimeToResolveSeconds is 2820s
    // (= 47m), not the 2280s (= 38m) used for the unrelated top-level KPI. formatDuration(2820)
    // is correctly "47m"; the assertion is corrected to match the given fixture value.
    expect(screen.getByText(/34 · 47m/)).toBeInTheDocument()
  })

  it('shows the error message when analytics fails', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'FORBIDDEN', message: 'Not permitted' } }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    mount()
    expect(await screen.findByText('Not permitted')).toBeInTheDocument()
  })
})
