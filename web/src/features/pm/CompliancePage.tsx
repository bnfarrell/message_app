import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCompliance } from '../../api/hooks/pm'
import type { ComplianceTemplateOut } from '../../api/types'
import { Badge, EmptyState, Input, Spinner } from '../../components/ui'
import { CADENCE_LABELS, KIND_LABELS, formatWindow, ordinal } from './labels'

const HEADING = 'text-xs font-bold uppercase tracking-widest text-text3'
const TH = 'border-b border-border2 px-3 py-2 text-left text-[11.5px] font-bold uppercase tracking-wider text-text3'
const TD = 'border-b border-border px-3 py-2 text-sm'

function localDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${value}%`
}

function TemplateCard({ template }: { template: ComplianceTemplateOut }) {
  const cycles = template.cycles ?? []
  return (
    <section className="rounded-card border border-border2 bg-surface p-4">
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-bold">{template.name}</h2>
        <Badge>{template.mode === 'sweep' ? 'Sweep' : 'Scheduled'}</Badge>
        {template.unitKind ? <span className="text-xs text-text3">{KIND_LABELS[template.unitKind]}</span> : null}
        <span className="ml-auto text-xs text-text3">Inspection pass rate {pct(template.inspectionPassRate)}</span>
      </header>
      {template.mode === 'sweep' ? (
        cycles.length === 0 ? (
          <p className="text-xs text-text3">No cycles in this window.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr>
                {['Cycle', 'Window', 'Passed', 'Missed', 'Total', 'On time'].map((h) => (
                  <th key={h} className={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cycles.map((cycle) => (
                <tr key={cycle.ordinal + cycle.startsOn}>
                  <td className={TD}>
                    {ordinal(cycle.ordinal)} Cycle{cycle.status === 'open' ? <span className="ml-2 text-xs text-text3">open</span> : null}
                  </td>
                  <td className={TD}>{formatWindow(cycle.startsOn, cycle.endsOn)}</td>
                  <td className={`${TD} font-mono`}>{cycle.passed}</td>
                  <td className={`${TD} font-mono`}>{cycle.missed}</td>
                  <td className={`${TD} font-mono`}>{cycle.total}</td>
                  <td className={`${TD} font-mono`}>{pct(cycle.onTimePct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : template.runs ? (
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ['Due', template.runs.due], ['Passed', template.runs.passed],
            ['Failed', template.runs.failed], ['Overdue', template.runs.overdue],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <dt className={HEADING}>{label}</dt>
              <dd className="font-mono text-lg font-bold">
                {value} {label === 'Overdue' ? 'overdue' : ''}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  )
}

export function CompliancePage() {
  const now = new Date()
  const [from, setFrom] = useState(`${now.getFullYear()}-01-01`)
  const [to, setTo] = useState(localDay(now))
  const { data, isPending, error } = useCompliance(from, to)
  const templates = data?.templates ?? []

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <Link to="/app/pm" className="text-sm font-semibold text-text3 hover:text-text">← Sweep</Link>
        <h1 className="text-base font-bold">PM Compliance</h1>
        <div className="ml-auto flex items-end gap-2">
          <div>
            <label className={HEADING} htmlFor="pm-from">From</label>
            <Input id="pm-from" type="date" className="h-9" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div>
            <label className={HEADING} htmlFor="pm-to">To</label>
            <Input id="pm-to" type="date" className="h-9" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </div>
      </header>
      {isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : error || !data ? (
        <EmptyState title="Could not load compliance" hint={error?.message} />
      ) : templates.length === 0 ? (
        <EmptyState title="No PM templates yet" />
      ) : (
        <div className="flex flex-col gap-4 p-4">
          {templates.map((template) => (
            <TemplateCard key={template.id} template={template} />
          ))}
          <p className="text-xs text-text3">
            Sweep cadences: {templates.filter((t) => t.mode === 'sweep').map((t) => t.name).join(', ') || 'none'} ·
            windows are property-local calendar {Object.values(CADENCE_LABELS).join('/').toLowerCase()} periods.
          </p>
        </div>
      )}
    </div>
  )
}
