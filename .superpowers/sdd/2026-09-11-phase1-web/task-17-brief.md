### Task 17: Analytics

**Files:**
- Create: `web/src/api/hooks/analytics.ts`, `web/src/features/analytics/AnalyticsPage.tsx`, `StatCard.tsx`, `BarChart.tsx`, `BarList.tsx`, `dateRange.ts`
- Modify: `web/src/routes.tsx`
- Test: `web/src/features/analytics/dateRange.test.ts`, `BarChart.test.tsx`, `AnalyticsPage.test.tsx`

**Interfaces:**
- Consumes: `api` / `qk` (Task 3), `formatDuration` (Task 10), primitives (Task 4).
- Produces:
  - `useOverview(from: string, to: string)` → `GET analytics/overview?from=&to=`, `useAgentStats(from, to)` → `GET analytics/agents?from=&to=`
  - `dateRange.ts`: `type RangeKey = 'today' | '7d' | '30d'`; `rangeFor(key: RangeKey, now: Date): { from: string; to: string }` returning `YYYY-MM-DD` strings
  - `StatCard({ label, value, sub })`, `BarChart({ buckets, labelOf, highlightOf })`, `BarList({ rows })`, `AnalyticsPage`

**The server accepts ISO dates or datetimes** and treats a bare `YYYY-MM-DD` `to` as end-of-day (`server/app/api/analytics.py:_parse`, `end_of_day=True`). So the client sends plain dates and gets inclusive days — no off-by-one on "today".

**No chart library (§5.0).** Bars are CSS: a flex row of columns, each `height: (count / max * 100)%`, `bg-accent`, `rounded-t`, with three faint `--border` gridlines behind. Past-SLA bars are the only red. Direct labels, no axis chrome beyond hour ticks `00 06 12 18 23`.

**Layout from `Analytics.dc.html`:** a header with the property name and the range buttons `Today · 7 days · 30 days` plus **Export** (shown only when `can('export')`); then a four-card KPI row — Conversations, First response, SLA breaches, Work orders closed; then `Inbound messages by hour`; then `Time to first reply` as a horizontal `BarList` with the over-SLA buckets in `--dangerText`; then the `Agents` table; then `Work orders by department`.

**KPI card copy, mapping `Overview` fields exactly:**

| Card | Value | Sub |
|---|---|---|
| Conversations | `conversations` | `{inboundMessages} in · {outboundMessages} out` |
| First response | `formatDuration(firstResponseP50Seconds)` | `p90 {formatDuration(firstResponseP90Seconds)}` |
| SLA breaches | `slaBreaches` | `{(slaBreachRate * 100).toFixed(1)}% of conversations` |
| Work orders closed | `workOrdersClosed` | `mean {formatDuration(meanTimeToResolveSeconds)} · {workOrdersFromConversations} from guest texts` |

A null `firstResponseP50Seconds` renders `—`, not `0s`: no data is not a fast response. **This distinction is the one thing most likely to be got wrong here.**

**Agents table** (`AgentStats`): Agent · Handled · p50 · p90 · Breaches · Quick replies (`quickReplyShare` as a percentage) · WOs raised. Agents and dept_staff get only their own row — `GET analytics/agents` already scopes by capability (`view_own_stats` vs `view_property_analytics`), so the client renders whatever comes back without its own filtering.

**The Analytics route is already capability-gated** in Task 8's `RequireCapability`, so this page may assume `view_property_analytics` for the overview. The agents table is the one part an agent can reach — via `view_own_stats` — but only through a future "my stats" entry point, not this route. Render it defensively: an empty array is an empty table, not a crash.

- [ ] **Step 1: Write `dateRange.ts` and its failing test**

```ts
export type RangeKey = 'today' | '7d' | '30d'

function iso(date: Date): string {
  // Local date parts, not UTC: "today" must mean the operator's today.
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** The server treats a bare date `to` as end-of-day, so these ranges are inclusive. */
export function rangeFor(key: RangeKey, now: Date = new Date()): { from: string; to: string } {
  const to = iso(now)
  if (key === 'today') return { from: to, to }
  const days = key === '7d' ? 6 : 29
  const start = new Date(now)
  start.setDate(start.getDate() - days)
  return { from: iso(start), to }
}

export const RANGE_LABELS: Record<RangeKey, string> = {
  today: 'Today',
  '7d': '7 days',
  '30d': '30 days',
}
```

`web/src/features/analytics/dateRange.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { rangeFor } from './dateRange'

const NOW = new Date(2026, 8, 10, 19, 4) // 10 Sep 2026, local

describe('rangeFor', () => {
  it('makes today a single inclusive day', () => {
    expect(rangeFor('today', NOW)).toEqual({ from: '2026-09-10', to: '2026-09-10' })
  })

  it('makes 7 days span seven days including today, not eight', () => {
    expect(rangeFor('7d', NOW)).toEqual({ from: '2026-09-04', to: '2026-09-10' })
  })

  it('makes 30 days span thirty days including today', () => {
    expect(rangeFor('30d', NOW)).toEqual({ from: '2026-08-12', to: '2026-09-10' })
  })

  it('crosses a month boundary correctly', () => {
    expect(rangeFor('7d', new Date(2026, 8, 2, 12, 0))).toEqual({
      from: '2026-08-27',
      to: '2026-09-02',
    })
  })

  it('crosses a year boundary correctly', () => {
    expect(rangeFor('7d', new Date(2027, 0, 3, 12, 0))).toEqual({
      from: '2026-12-28',
      to: '2027-01-03',
    })
  })

  it('uses local date parts, so a late-evening call does not roll to tomorrow', () => {
    expect(rangeFor('today', new Date(2026, 8, 10, 23, 59)).to).toBe('2026-09-10')
  })
})
```

- [ ] **Step 2: Write `web/src/api/hooks/analytics.ts`**

```ts
import { useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { AgentStats, Overview } from '../types'

export function useOverview(from: string, to: string) {
  const { propertyId } = useSession()
  return useQuery<Overview, ApiError>({
    queryKey: qk.analyticsOverview(propertyId, from, to),
    queryFn: () => api<Overview>(propertyPath(propertyId, `analytics/overview?from=${from}&to=${to}`)),
    staleTime: 60_000,
  })
}

export function useAgentStats(from: string, to: string) {
  const { propertyId } = useSession()
  return useQuery<AgentStats[], ApiError>({
    queryKey: qk.analyticsAgents(propertyId, from, to),
    queryFn: () => api<AgentStats[]>(propertyPath(propertyId, `analytics/agents?from=${from}&to=${to}`)),
    staleTime: 60_000,
  })
}
```

- [ ] **Step 3: Write the failing chart test**

`web/src/features/analytics/BarChart.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BarChart } from './BarChart'

const BUCKETS = [
  { hour: 0, count: 2 },
  { hour: 1, count: 0 },
  { hour: 18, count: 31 },
  { hour: 19, count: 14 },
]

describe('BarChart', () => {
  it('renders one bar per bucket', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    expect(screen.getAllByTestId('bar')).toHaveLength(4)
  })

  it('scales the tallest bar to full height', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    const bars = screen.getAllByTestId('bar')
    expect(bars[2]!.style.height).toBe('100%')
  })

  it('scales the others proportionally', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    // 14 of 31 ≈ 45.2%
    expect(parseFloat(screen.getAllByTestId('bar')[3]!.style.height)).toBeCloseTo(45.2, 0)
  })

  it('gives a zero bucket zero height without dividing by anything', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    expect(screen.getAllByTestId('bar')[1]!.style.height).toBe('0%')
  })

  it('survives an all-zero series rather than rendering NaN', () => {
    render(
      <BarChart buckets={[{ hour: 0, count: 0 }, { hour: 1, count: 0 }]} labelOf={(b) => `${b.hour}`} />,
    )
    for (const bar of screen.getAllByTestId('bar')) expect(bar.style.height).toBe('0%')
  })

  it('renders nothing for an empty series', () => {
    const { container } = render(<BarChart buckets={[]} labelOf={() => ''} />)
    expect(container.querySelectorAll('[data-testid="bar"]')).toHaveLength(0)
  })

  it('labels each bar for assistive tech and hover', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00 · ${b.count} messages`} />)
    expect(screen.getByTitle('18:00 · 31 messages')).toBeInTheDocument()
  })

  it('paints a highlighted bar in danger, the only red allowed', () => {
    render(
      <BarChart
        buckets={BUCKETS}
        labelOf={(b) => `${b.hour}`}
        highlightOf={(b) => b.hour === 19}
      />,
    )
    const bars = screen.getAllByTestId('bar')
    expect(bars[3]!.className).toContain('bg-danger')
    expect(bars[2]!.className).toContain('bg-accent')
  })
})
```

- [ ] **Step 4: Write `BarChart.tsx`, `BarList.tsx` and `StatCard.tsx`**

```tsx
// BarChart.tsx
import { cn } from '../../lib/cn'

export function BarChart<T extends { count: number }>({
  buckets,
  labelOf,
  highlightOf,
  height = 160,
}: {
  buckets: T[]
  labelOf: (bucket: T) => string
  highlightOf?: (bucket: T) => boolean
  height?: number
}) {
  // An all-zero series must not divide by zero; a max of 1 keeps every bar at 0%.
  const max = Math.max(1, ...buckets.map((b) => b.count))

  return (
    <div className="relative" style={{ height }}>
      {[0.25, 0.5, 0.75].map((fraction) => (
        <div
          key={fraction}
          aria-hidden="true"
          className="absolute left-0 right-0 h-px bg-border"
          style={{ bottom: `${fraction * 100}%` }}
        />
      ))}
      <div className="flex h-full items-end gap-[3px]">
        {buckets.map((bucket, index) => (
          <div key={index} className="flex h-full flex-1 items-end" title={labelOf(bucket)}>
            <div
              data-testid="bar"
              className={cn(
                'w-full rounded-t',
                highlightOf?.(bucket) ? 'bg-danger' : 'bg-accent',
              )}
              style={{ height: `${(bucket.count / max) * 100}%` }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
```

```tsx
// BarList.tsx — horizontal bars with direct labels (the mockup's .hbar)
import { cn } from '../../lib/cn'

export function BarList({
  rows,
}: {
  rows: { label: string; value: string; share: number; danger?: boolean }[]
}) {
  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((row) => (
        <li key={row.label} className="flex items-center gap-3">
          <span className="w-16 flex-none text-xs text-text3">{row.label}</span>
          <span className="flex h-2.5 flex-1 overflow-hidden rounded-r bg-surface2">
            <span
              className={cn('h-2.5 rounded-r', row.danger ? 'bg-danger' : 'bg-accent')}
              style={{ width: `${Math.min(100, row.share * 100)}%` }}
            />
          </span>
          <span
            className={cn('w-12 flex-none text-right font-mono text-xs', row.danger && 'text-dangerText')}
          >
            {row.value}
          </span>
        </li>
      ))}
    </ul>
  )
}
```

```tsx
// StatCard.tsx
export function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-card border border-border2 bg-surface p-4">
      <p className="text-[13px] font-bold uppercase tracking-wider text-text3">{label}</p>
      <p className="font-mono text-3xl font-bold leading-none tracking-tight">{value}</p>
      {sub ? <p className="text-[12.5px] text-text3">{sub}</p> : null}
    </div>
  )
}
```

- [ ] **Step 5: Write `AnalyticsPage.tsx`**

```tsx
import { useMemo, useState } from 'react'
import { useAgentStats, useOverview } from '../../api/hooks/analytics'
import { useSession } from '../../auth/SessionContext'
import { Button, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { formatDuration } from '../../lib/time'
import { BarChart } from './BarChart'
import { BarList } from './BarList'
import { RANGE_LABELS, rangeFor, type RangeKey } from './dateRange'
import { StatCard } from './StatCard'

/** No data is not a fast response — never render a null duration as 0s. */
function duration(seconds: number | null | undefined): string {
  return seconds === null || seconds === undefined ? '—' : formatDuration(seconds)
}

const CARD = 'rounded-card border border-border2 bg-surface p-4'
const H = 'mb-3 text-[13px] font-bold uppercase tracking-wider text-text3'

export function AnalyticsPage() {
  const { membership, can } = useSession()
  const [key, setKey] = useState<RangeKey>('7d')
  const { from, to } = useMemo(() => rangeFor(key), [key])
  const overview = useOverview(from, to)
  const agents = useAgentStats(from, to)

  if (overview.isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (overview.error || !overview.data) {
    return <EmptyState title="Could not load analytics" hint={overview.error?.message} />
  }
  const d = overview.data

  return (
    <div className="h-full overflow-y-auto p-4">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-base font-bold">Analytics</h1>
          <p className="text-xs text-text3">{membership.propertyName}</p>
        </div>
        <div role="tablist" className="ml-4 flex gap-1.5">
          {(Object.keys(RANGE_LABELS) as RangeKey[]).map((option) => (
            <button
              key={option}
              role="tab"
              aria-selected={key === option}
              onClick={() => setKey(option)}
              className={cn(
                'inline-flex h-10 items-center rounded px-3.5 text-[13.5px] font-semibold',
                key === option ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
              )}
            >
              {RANGE_LABELS[option]}
            </button>
          ))}
        </div>
        {can('export') ? (
          <Button
            className="ml-auto"
            onClick={() => {
              // The server has no export endpoint in Phase 1; CSV from what is on screen
              // is honest and needs no new API surface.
              const rows = [
                ['metric', 'value'],
                ['conversations', String(d.conversations)],
                ['inboundMessages', String(d.inboundMessages)],
                ['outboundMessages', String(d.outboundMessages)],
                ['firstResponseP50Seconds', String(d.firstResponseP50Seconds ?? '')],
                ['firstResponseP90Seconds', String(d.firstResponseP90Seconds ?? '')],
                ['slaBreaches', String(d.slaBreaches)],
                ['slaBreachRate', String(d.slaBreachRate)],
                ['workOrdersClosed', String(d.workOrdersClosed)],
              ]
              const csv = rows.map((r) => r.join(',')).join('\n')
              const link = document.createElement('a')
              link.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`
              link.download = `analytics-${from}-to-${to}.csv`
              link.click()
            }}
          >
            Export
          </Button>
        ) : null}
      </header>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Conversations"
          value={String(d.conversations)}
          sub={`${d.inboundMessages} in · ${d.outboundMessages} out`}
        />
        <StatCard
          label="First response"
          value={duration(d.firstResponseP50Seconds)}
          sub={`p90 ${duration(d.firstResponseP90Seconds)}`}
        />
        <StatCard
          label="SLA breaches"
          value={String(d.slaBreaches)}
          sub={`${(d.slaBreachRate * 100).toFixed(1)}% of conversations`}
        />
        <StatCard
          label="Work orders closed"
          value={String(d.workOrdersClosed)}
          sub={`mean ${duration(d.meanTimeToResolveSeconds)} · ${d.workOrdersFromConversations} from guest texts`}
        />
      </div>

      <div className="mb-4 grid gap-3 lg:grid-cols-2">
        <section className={CARD}>
          <h2 className={H}>Inbound messages by hour</h2>
          <BarChart
            buckets={d.inboundByHour}
            labelOf={(b) => `${String(b.hour).padStart(2, '0')}:00 · ${b.count} messages`}
          />
          <div className="mt-2 flex justify-between font-mono text-[11px] text-text4">
            {['00', '06', '12', '18', '23'].map((tick) => (
              <span key={tick}>{tick}</span>
            ))}
          </div>
        </section>

        <section className={CARD}>
          <h2 className={H}>Time to first reply</h2>
          <BarList
            rows={d.firstResponseDistribution.map((bucket) => ({
              label: bucket.label,
              value: `${Math.round(bucket.share * 100)}%`,
              share: bucket.share,
              // The only red: buckets past the 15-minute SLA.
              danger: bucket.label.includes('15') || bucket.label.includes('30'),
            }))}
          />
          <p className="mt-3 text-[12.5px] text-text3">Red is past the 15-minute SLA.</p>
        </section>
      </div>

      <section className={`${CARD} mb-4`}>
        <h2 className={H}>Agents</h2>
        {agents.isPending ? (
          <Spinner />
        ) : (agents.data ?? []).length === 0 ? (
          <p className="text-xs text-text3">No agent activity in this range.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr>
                {['Agent', 'Handled', 'p50', 'p90', 'Breaches', 'Quick replies', 'WOs raised'].map(
                  (head) => (
                    <th
                      key={head}
                      className="border-b border-border2 px-2 py-1.5 text-left text-[11.5px] font-bold uppercase tracking-wider text-text3"
                    >
                      {head}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {(agents.data ?? []).map((agent) => (
                <tr key={agent.userId}>
                  <td className="border-b border-border px-2 py-2.5 text-[13.5px] font-semibold">{agent.name}</td>
                  <td className="border-b border-border px-2 py-2.5 font-mono text-[13.5px]">{agent.conversationsHandled}</td>
                  <td className="border-b border-border px-2 py-2.5 font-mono text-[13.5px]">{duration(agent.firstResponseP50Seconds)}</td>
                  <td className="border-b border-border px-2 py-2.5 font-mono text-[13.5px]">{duration(agent.firstResponseP90Seconds)}</td>
                  <td className={cn('border-b border-border px-2 py-2.5 font-mono text-[13.5px]', agent.slaBreaches > 0 && 'text-dangerText')}>
                    {agent.slaBreaches}
                  </td>
                  <td className="border-b border-border px-2 py-2.5 font-mono text-[13.5px]">
                    {agent.quickReplyShare === null || agent.quickReplyShare === undefined
                      ? '—'
                      : `${Math.round(agent.quickReplyShare * 100)}%`}
                  </td>
                  <td className="border-b border-border px-2 py-2.5 font-mono text-[13.5px]">{agent.workOrdersCreated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className={CARD}>
        <h2 className={H}>Work orders by department</h2>
        {d.workOrdersByDepartment.length === 0 ? (
          <p className="text-xs text-text3">Nothing closed in this range.</p>
        ) : (
          <BarList
            rows={d.workOrdersByDepartment.map((bucket) => {
              const max = Math.max(1, ...d.workOrdersByDepartment.map((b) => b.closed))
              return {
                label: bucket.departmentName,
                value: `${bucket.closed} · ${duration(bucket.meanTimeToResolveSeconds)}`,
                share: bucket.closed / max,
              }
            })}
          />
        )}
      </section>
    </div>
  )
}
```

- [ ] **Step 6: Write `AnalyticsPage.test.tsx`**

```tsx
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
    expect(screen.getByText(/34 · 38m/)).toBeInTheDocument()
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
```

- [ ] **Step 7: Run the tests, wire the route, verify**

```bash
cd web && npx vitest run src/features/analytics
```

Expected: FAIL first (modules missing), then PASS — 6 range tests, 8 chart tests, 12 page tests — once Steps 1-6 are in. Replace the Analytics placeholder in `routes.tsx` with `<AnalyticsPage />`.

Then, against the real server as `morgan@hvh.test`: the cards fill from the seeded 3 days of messages, the hour chart peaks in the late afternoon, the reply distribution's over-SLA buckets are red, and the agents table lists Ava, Marcus and Jordan. Switch to **Today** and **30 days** and confirm the numbers change. Sign in as `alex@hvh.test` and confirm **Export** downloads a CSV.

- [ ] **Step 8: Commit**

```bash
git add web/src/features/analytics web/src/api/hooks/analytics.ts web/src/routes.tsx
git commit -m "feat(web): analytics with CSS bars, honest null handling and role-gated export"
```

---

