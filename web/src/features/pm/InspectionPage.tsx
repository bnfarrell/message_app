import { Link, useSearchParams } from 'react-router-dom'
import { useInspections } from '../../api/hooks/pm'
import type { InspectionRowOut, PmUnitKind } from '../../api/types'
import { Badge, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { formatClock } from '../../lib/time'
import { KindTabs } from './KindTabs'
import { KIND_LABELS, RUN_STATUS_LABELS, isKind } from './labels'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'

function Row({ row }: { row: InspectionRowOut }) {
  return (
    <li>
      <Link
        to={`/app/pm/runs/${row.runId}`}
        className="flex flex-wrap items-center gap-3 rounded-card border border-border2 bg-surface p-3 hover:bg-surface2"
      >
        <span className="font-mono text-sm font-bold text-roomNum">{row.unitCode}</span>
        <span className="text-sm font-semibold">{row.unitName}</span>
        <span className="text-xs text-text3">{row.templateName}</span>
        <span className="w-full text-xs text-text3 md:ml-auto md:w-auto">
          {row.completedByName ?? 'Unknown'}
          {row.completedAt ? ` · ${formatClock(row.completedAt)}` : ''}
          {' · '}
          {row.daysSinceLastPm === null || row.daysSinceLastPm === undefined
            ? 'never inspected before'
            : `${row.daysSinceLastPm} days since last PM`}
        </span>
        {row.status !== 'completed' ? (
          <span className="flex items-center gap-2 text-xs text-text3">
            <Badge tone={row.status === 'passed' ? 'ok' : 'danger'}>{RUN_STATUS_LABELS[row.status]}</Badge>
            {row.inspectedByName}
          </span>
        ) : null}
      </Link>
    </li>
  )
}

export function InspectionPage() {
  const [params, setParams] = useSearchParams()
  const kindParam = params.get('kind')
  const kind: PmUnitKind | 'all' = isKind(kindParam) ? kindParam : 'all'
  const tab = params.get('tab') === 'inspected' ? 'inspected' : 'available'
  const sort: 'days_since_last_pm' | 'completed_at' =
    params.get('sort') === 'days_since_last_pm' ? 'days_since_last_pm' : 'completed_at'
  const scope = { kind: kind === 'all' ? null : kind, sort }
  const available = useInspections({ ...scope, status: 'available' })
  const inspected = useInspections({ ...scope, status: 'inspected' })
  const current = tab === 'available' ? available : inspected

  function set(next: Record<string, string | null>) {
    const merged = new URLSearchParams(params)
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value)
      else merged.delete(key)
    }
    setParams(merged)
  }

  const subTab = (key: 'available' | 'inspected', label: string, count: number | undefined) => (
    <button
      type="button"
      role="tab"
      aria-selected={tab === key}
      onClick={() => set({ tab: key === 'available' ? null : key })}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded px-3 text-sm font-semibold',
        tab === key ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
      )}
    >
      {label}
      <span className="font-mono text-xs opacity-85">{count ?? '…'}</span>
    </button>
  )

  const kindLabel = kind === 'all' ? '' : `${KIND_LABELS[kind].toLowerCase()} `

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">PM Inspection</h1>
      </header>
      <KindTabs allowAll value={kind} onChange={(next) => set({ kind: next === 'all' ? null : next })} />
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        <div role="tablist" className="flex gap-1.5">
          {subTab('available', 'Available for Inspection', available.data?.length)}
          {subTab('inspected', 'Inspected', inspected.data?.length)}
        </div>
        <label className="ml-auto flex items-center gap-2 text-xs font-semibold text-text3">
          Sort
          <select className={SELECT} value={sort}
                  onChange={(event) => set({ sort: event.target.value === 'completed_at' ? null : event.target.value })}>
            <option value="completed_at">Completed</option>
            <option value="days_since_last_pm">Days since last PM</option>
          </select>
        </label>
      </div>

      {current.isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : current.error ? (
        <EmptyState title="Could not load the queue" hint={current.error.message} />
      ) : current.data.length === 0 ? (
        <EmptyState
          title={tab === 'available' ? `No ${kindLabel}PMs are pending for inspection` : `No ${kindLabel}PMs have been inspected`}
        />
      ) : (
        <ul className="flex flex-col gap-2 p-4">
          {current.data.map((row) => (
            <Row key={row.runId} row={row} />
          ))}
        </ul>
      )}
    </div>
  )
}
