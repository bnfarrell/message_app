import type { ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useStartRun, useSweep } from '../../api/hooks/pm'
import type { PmUnitKind, SweepUnitOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, EmptyState, Input, Spinner, useToast } from '../../components/ui'
import { cn } from '../../lib/cn'
import { useMediaQuery } from '../../lib/useMediaQuery'
import { KindTabs } from './KindTabs'
import { CADENCE_LABELS, KIND_LABELS, formatWindow, isKind, ordinal } from './labels'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'
const HEADING = 'text-xs font-bold uppercase tracking-widest text-text3'

const TILE_TONES = {
  danger: 'bg-dangerBg text-dangerText',
  note: 'bg-noteBg text-noteText',
  ok: 'bg-okBg text-okText',
} as const

function Tile({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub?: string
  tone: keyof typeof TILE_TONES
}) {
  return (
    <div className={cn('flex min-w-[160px] flex-1 flex-col rounded-card p-4', TILE_TONES[tone])}>
      <span className="text-xs font-bold uppercase tracking-widest opacity-80">{label}</span>
      <span className="mt-1 text-2xl font-bold">{value}</span>
      {sub ? <span className="text-xs opacity-80">{sub}</span> : null}
    </div>
  )
}

function lastPm(unit: SweepUnitOut): string {
  if (!unit.lastPassedAt) return 'Never'
  const when = new Date(unit.lastPassedAt).toLocaleDateString()
  return unit.lastPassedByName ? `${when} · ${unit.lastPassedByName}` : when
}

function csvCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function toCsv(rows: SweepUnitOut[]): string {
  const header = 'code,name,floor,room_type,last_pm,last_pm_by,status'
  const lines = rows.map((u) =>
    [
      u.code, u.name, u.floor, u.roomType, u.lastPassedAt, u.lastPassedByName,
      u.passedThisCycle ? 'done' : u.currentRun?.status ?? 'remaining',
    ].map(csvCell).join(','),
  )
  return [header, ...lines].join('\n') + '\n'
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function SweepPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { can } = useSession()
  const toast = useToast()
  const isMobile = useMediaQuery('(max-width: 767px)')

  const kindParam = params.get('kind')
  const kind: PmUnitKind = isKind(kindParam) ? kindParam : 'guest_room'
  const statusParam = params.get('status')
  const status = statusParam === 'remaining' || statusParam === 'completed' ? statusParam : null
  const sort = params.get('sort') ?? 'code'
  const q = params.get('q') ?? ''

  const { data, isPending, error } = useSweep({ kind, status, sort, q })
  const startRun = useStartRun()

  function set(next: Record<string, string | null>) {
    const merged = new URLSearchParams(params)
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value)
      else merged.delete(key)
    }
    setParams(merged)
  }

  function start(unit: SweepUnitOut) {
    if (!data?.template) return
    startRun.mutate(
      { templateId: data.template.id, unitId: unit.id },
      {
        onSuccess: (run) => navigate(`/app/pm/runs/${run.id}`),
        onError: (err) => {
          // Somebody else started this unit first: the 409 names their run, so join it.
          const runId = (err.details as { runId?: string } | undefined)?.runId
          if (err.status === 409 && runId) navigate(`/app/pm/runs/${runId}`)
          else toast(err.message, 'danger')
        },
      },
    )
  }

  const action = (unit: SweepUnitOut) => {
    if (unit.passedThisCycle) return <Button disabled>Done</Button>
    const run = unit.currentRun
    if (run?.status === 'completed') return <Button disabled>Awaiting inspection</Button>
    if (run) {
      return (
        <Button onClick={() => navigate(`/app/pm/runs/${run.id}`)}>
          Continue{run.startedByName ? ` · ${run.startedByName}` : ''}
        </Button>
      )
    }
    if (!can('perform_pm')) return null
    return (
      <Button variant="primary" loading={startRun.isPending} onClick={() => start(unit)}>
        Start
      </Button>
    )
  }

  let body: ReactNode
  if (isPending) {
    body = (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  } else if (error || !data) {
    body = <EmptyState title="Could not load the sweep" hint={error?.message} />
  } else if (!data.template) {
    body = (
      <EmptyState
        title={`No sweep template for ${KIND_LABELS[kind]}`}
        hint="A sweep template says how often every unit of this kind gets its PM and what the checklist is."
        action={
          can('manage_admin') ? (
            <Link to="/app/admin/pm-templates" className="text-sm font-semibold text-accent hover:underline">
              Set one up under PM templates
            </Link>
          ) : null
        }
      />
    )
  } else if (!data.cycle) {
    body = <EmptyState title="No open cycle yet" hint="The next cycle opens on its window's first day." />
  } else if (!data.units || data.units.length === 0) {
    body = (
      <EmptyState
        title={q || status ? 'Nothing matches' : `No active ${KIND_LABELS[kind].toLowerCase()}`}
        hint={q || status ? 'Clear the search or filter.' : 'Add units under Admin → Maintainable units.'}
      />
    )
  } else if (isMobile) {
    body = (
      <ul className="flex flex-col gap-2 p-4">
        {data.units.map((unit) => (
          <li key={unit.id} className="flex items-center gap-3 rounded-card border border-border2 bg-surface p-3">
            <div className="min-w-0 flex-1">
              <p className="font-mono text-sm font-bold text-roomNum">{unit.code}</p>
              <p className="truncate text-sm">{unit.name}</p>
              <p className="text-xs text-text3">Last PM: {lastPm(unit)}</p>
            </div>
            {action(unit)}
          </li>
        ))}
      </ul>
    )
  } else {
    body = (
      <div className="p-4">
        <table className="w-full">
          <thead>
            <tr>
              {['Unit', 'Floor', 'Last PM', ''].map((head) => (
                <th key={head} className="border-b border-border2 px-3.5 py-2.5 text-left text-[11.5px] font-bold uppercase tracking-wider text-text3">
                  {head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.units.map((unit) => (
              <tr key={unit.id}>
                <td className="border-b border-border px-3.5 py-3">
                  <span className="font-mono text-sm font-bold text-roomNum">{unit.code}</span>
                  <span className="ml-2 text-sm">{unit.name}</span>
                  {unit.roomType ? <span className="ml-2 text-xs text-text3">({unit.roomType})</span> : null}
                </td>
                <td className="border-b border-border px-3.5 py-3 text-sm">{unit.floor ?? '—'}</td>
                <td className="border-b border-border px-3.5 py-3 text-sm text-text2">{lastPm(unit)}</td>
                <td className="border-b border-border px-3.5 py-3 text-right">{action(unit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Preventative Maintenance</h1>
        {data?.template ? (
          <span className="text-xs text-text3">
            {data.template.name} · {CADENCE_LABELS[data.template.cadence]}
          </span>
        ) : null}
        {can('view_property_analytics') ? (
          <Link to="/app/pm/compliance" className="ml-auto text-sm font-semibold text-text3 hover:text-text">
            Compliance →
          </Link>
        ) : null}
      </header>

      <KindTabs value={kind} onChange={(next) => set({ kind: next === 'all' ? null : next })} />

      {data?.cycle ? (
        <div className="flex flex-wrap gap-3 p-4">
          <Tile label="Remaining" value={String(data.counts.remaining)} tone="danger" />
          <Tile
            label={`${ordinal(data.cycle.ordinal)} Cycle`}
            value={`${data.cycle.daysLeft} days`}
            sub={formatWindow(data.cycle.startsOn, data.cycle.endsOn)}
            tone="note"
          />
          <Tile label="Completed" value={String(data.counts.completed)} tone="ok" />
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
        <div className="min-w-[200px] flex-1">
          <label className={HEADING} htmlFor="pm-sweep-q">Search</label>
          <Input
            id="pm-sweep-q"
            className="h-9"
            placeholder="Room, area or equipment"
            value={q}
            onChange={(event) => set({ q: event.target.value })}
          />
        </div>
        <div>
          <label className={HEADING} htmlFor="pm-sweep-status">Show</label>
          <select id="pm-sweep-status" className={SELECT} value={status ?? ''}
                  onChange={(event) => set({ status: event.target.value || null })}>
            <option value="">All</option>
            <option value="remaining">Remaining</option>
            <option value="completed">Completed</option>
          </select>
        </div>
        <div>
          <label className={HEADING} htmlFor="pm-sweep-sort">Sort</label>
          <select id="pm-sweep-sort" className={SELECT} value={sort}
                  onChange={(event) => set({ sort: event.target.value === 'code' ? null : event.target.value })}>
            <option value="code">Unit</option>
            <option value="floor">Floor</option>
            <option value="days_since_last_pm">Days since last PM</option>
          </select>
        </div>
        {can('export') && data?.units?.length ? (
          <Button onClick={() => download(`pm-${kind}.csv`, toCsv(data.units!))}>Export</Button>
        ) : null}
      </div>

      {body}
    </div>
  )
}
