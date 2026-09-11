import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAgentStats, useOverview } from '../../api/hooks/analytics'
import { useSession } from '../../auth/SessionContext'
import { Button, EmptyState, Input, Spinner } from '../../components/ui'
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

// The server's stable bucket order (see app/domain/analytics.py) — only these two are past
// the 15-minute SLA. Matched by exact label, not substring: "5–15 min" contains "15" too.
const PAST_SLA_LABELS = new Set(['15–30 min', '30+ min'])

export function AnalyticsPage() {
  const { membership, can } = useSession()
  const [searchParams, setSearchParams] = useSearchParams()
  const keyParam = (searchParams.get('range') ?? '7d') as RangeKey
  const [key, setKey] = useState<RangeKey>(keyParam)
  const [customFrom, setCustomFrom] = useState(searchParams.get('from') ?? '')
  const [customTo, setCustomTo] = useState(searchParams.get('to') ?? '')

  const handleRangeChange = (newKey: RangeKey) => {
    setKey(newKey)
    const newParams = new URLSearchParams(searchParams)
    newParams.set('range', newKey)
    if (newKey !== 'custom') {
      newParams.delete('from')
      newParams.delete('to')
    }
    setSearchParams(newParams)
  }

  const handleCustomDateChange = (from: string, to: string) => {
    setCustomFrom(from)
    setCustomTo(to)
    if (from && to) {
      const newParams = new URLSearchParams(searchParams)
      newParams.set('from', from)
      newParams.set('to', to)
      setSearchParams(newParams)
    }
  }

  const isValidRange = key !== 'custom' || Boolean(customFrom && customTo && customFrom <= customTo)
  const { from, to } = useMemo(
    () => (isValidRange ? rangeFor(key, new Date(), customFrom, customTo) : { from: '', to: '' }),
    [key, customFrom, customTo, isValidRange],
  )
  const overview = useOverview(from, to, isValidRange)
  const agents = useAgentStats(from, to, isValidRange)
  const d = overview.data

  const header = (
    <header className="mb-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
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
              onClick={() => handleRangeChange(option)}
              className={cn(
                'inline-flex h-10 items-center rounded px-3.5 text-[13.5px] font-semibold',
                key === option ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
              )}
            >
              {RANGE_LABELS[option]}
            </button>
          ))}
        </div>
        {can('export') && d ? (
          <Button
            className="ml-auto"
            onClick={() => {
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
      </div>
      {key === 'custom' && (
        <div className="flex gap-2">
          <Input
            type="date"
            value={customFrom}
            onChange={(e) => handleCustomDateChange(e.target.value, customTo)}
            className="w-32"
          />
          <Input
            type="date"
            value={customTo}
            onChange={(e) => handleCustomDateChange(customFrom, e.target.value)}
            className="w-32"
          />
          {customFrom && customTo && customFrom > customTo && (
            <p className="flex items-center text-xs text-dangerText">From date cannot be after to date</p>
          )}
        </div>
      )}
    </header>
  )

  if (!isValidRange) {
    return (
      <div className="h-full overflow-y-auto p-4">
        {header}
        <p className="text-xs text-text3">Enter a valid date range to see analytics.</p>
      </div>
    )
  }

  if (overview.isPending) {
    return (
      <div className="h-full overflow-y-auto p-4">
        {header}
        <div className="grid place-items-center py-12">
          <Spinner />
        </div>
      </div>
    )
  }
  if (overview.error || !d) {
    return (
      <div className="h-full overflow-y-auto p-4">
        {header}
        <EmptyState title="Could not load analytics" hint={overview.error?.message} />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      {header}

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
              danger: PAST_SLA_LABELS.has(bucket.label),
            }))}
          />
          <p className="mt-3 text-[12.5px] text-text3">Red is past the 15-minute SLA.</p>
        </section>
      </div>

      <section className={`${CARD} mb-4`}>
        <h2 className={H}>Agents</h2>
        {agents.isPending ? (
          <Spinner />
        ) : agents.error ? (
          <EmptyState title="Could not load agent activity" hint={agents.error.message} />
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
