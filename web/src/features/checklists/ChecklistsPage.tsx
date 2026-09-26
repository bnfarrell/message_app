import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  useAssignChecklist,
  useChecklistInstances,
  useChecklistTemplates,
  useMissedChecklists,
  useStartChecklist,
  useStartOnDemand,
} from '../../api/hooks/checklists'
import { useDepartments } from '../../api/hooks/users'
import { useStaffDirectory } from '../../api/hooks/staffMessages'
import type { ChecklistInstanceRowOut, Shift } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Badge, Button, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { KIND_LABELS, SHIFT_LABELS, STATUS_LABELS, STATUS_TONE } from './labels'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'

const SHIFT_ORDER: Shift[] = ['am', 'pm', 'overnight']

function AssignSelect({
  row,
  departmentId,
  assign,
}: {
  row: ChecklistInstanceRowOut
  departmentId: string
  assign: ReturnType<typeof useAssignChecklist>
}) {
  const { data: staff } = useStaffDirectory()
  const members = (staff ?? []).filter((s) => s.departmentId === departmentId)
  return (
    <select
      aria-label={`Assign ${row.templateName}`}
      className={SELECT}
      value={row.assignedUserId ?? ''}
      onChange={(event) =>
        assign.mutate({ instanceId: row.id, userId: event.target.value || null })
      }
    >
      <option value="">Unassigned</option>
      {members.map((m) => (
        <option key={m.userId} value={m.userId}>
          {m.firstName} {m.lastName}
        </option>
      ))}
    </select>
  )
}

function ChecklistCard({ row }: { row: ChecklistInstanceRowOut }) {
  const { can, membership, user } = useSession()
  const navigate = useNavigate()
  const start = useStartChecklist()
  const assign = useAssignChecklist()
  const canStart =
    row.status === 'open' &&
    can('perform_checklists') &&
    (can('manage_checklists') ||
      membership.departmentId === row.departmentId ||
      row.assignedUserId === user.id)

  return (
    <li className="flex flex-col gap-2 rounded-card border border-border2 bg-surface p-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold">{row.templateName}</span>
        {row.kind === 'readings' ? <Badge tone="note">{KIND_LABELS.readings}</Badge> : null}
        <span className="text-xs text-text3">{row.departmentName}</span>
        <Badge tone={STATUS_TONE[row.status]}>{STATUS_LABELS[row.status]}</Badge>
        <span className="text-xs text-text3">{row.assignedName ?? 'Unassigned'}</span>
        <span className="text-xs text-text3">
          {row.done} / {row.total}
        </span>
        {row.outOfRangeCount > 0 ? (
          <span className="text-xs text-dangerText">{row.outOfRangeCount} out of range</span>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          {can('manage_checklists') && (row.status === 'open' || row.status === 'in_progress') ? (
            <AssignSelect row={row} departmentId={row.departmentId} assign={assign} />
          ) : null}
          {canStart ? (
            <Button
              variant="primary"
              loading={start.isPending}
              onClick={() => start.mutate(row.id, { onSuccess: () => navigate(`/app/checklists/${row.id}`) })}
            >
              Start
            </Button>
          ) : (
            <Link to={`/app/checklists/${row.id}`}>
              <Button>{row.status === 'in_progress' ? 'Continue' : 'View'}</Button>
            </Link>
          )}
        </div>
      </div>
      {start.error ? <p role="alert" className="text-sm text-dangerText">{start.error.message}</p> : null}
      {assign.error ? <p role="alert" className="text-sm text-dangerText">{assign.error.message}</p> : null}
    </li>
  )
}

function StartOnDemand() {
  const { can, membership } = useSession()
  const navigate = useNavigate()
  const { data: templates } = useChecklistTemplates()
  const startOnDemand = useStartOnDemand()

  // Rendered only once templates have loaded, so the label never appears with an empty,
  // not-yet-populated menu behind it.
  if (!templates) return null

  const options = templates.filter(
    (t) =>
      t.schedule === 'on_demand' &&
      t.active &&
      (can('manage_checklists') || t.departmentId === membership.departmentId),
  )

  return (
    <div className="flex items-center gap-2">
      <label className="flex items-center gap-2 text-xs font-semibold text-text3">
        Start a checklist
        <select
          aria-label="Start a checklist"
          className={SELECT}
          value=""
          onChange={(event) => {
            const templateId = event.target.value
            if (!templateId) return
            startOnDemand.mutate(templateId, {
              onSuccess: (instance) => navigate(`/app/checklists/${instance.id}`),
            })
          }}
        >
          <option value="" disabled>
            Choose one
          </option>
          {options.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      {startOnDemand.error ? (
        <p role="alert" className="text-sm text-dangerText">{startOnDemand.error.message}</p>
      ) : null}
    </div>
  )
}

function MissedList() {
  const { data, isPending, error } = useMissedChecklists(true)

  if (isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }
  if (error) return <EmptyState title="Could not load missed checklists" hint={error.message} />
  if (data.length === 0) return <EmptyState title="No missed checklists" />

  return (
    <ul className="flex flex-col gap-2 p-4">
      {data.map((row) => (
        <li
          key={row.id}
          className="flex flex-wrap items-center gap-2 rounded-card border border-border2 bg-surface p-3 text-sm"
        >
          <span>{row.dueDate}</span>
          <span>{SHIFT_LABELS[row.shift]}</span>
          <span>{row.departmentName}</span>
          <span>{row.templateName}</span>
          <span>{row.assignedName ?? 'Unassigned'}</span>
        </li>
      ))}
    </ul>
  )
}

export function ChecklistsPage() {
  const { can, membership } = useSession()
  const { data: departments } = useDepartments()
  const [departmentId, setDepartmentId] = useState(membership.departmentId ?? '')
  const [tab, setTab] = useState<'today' | 'missed'>('today')
  const canSeeMissed = can('view_property_analytics')

  const { data, isPending, error } = useChecklistInstances({
    departmentId: departmentId || null,
  })

  const groups = SHIFT_ORDER.map((shift) => ({
    shift,
    rows: (data ?? []).filter((row) => row.shift === shift),
  })).filter((group) => group.rows.length > 0)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Checklists</h1>
        <label className="flex items-center gap-2 text-xs font-semibold text-text3">
          Department
          <select
            aria-label="Department"
            className={SELECT}
            value={departmentId}
            onChange={(event) => setDepartmentId(event.target.value)}
          >
            <option value="">All departments</option>
            {(departments ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <div className="ml-auto">
          <StartOnDemand />
        </div>
      </header>

      <div className="flex gap-1.5 border-b border-border px-4 py-3" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'today'}
          onClick={() => setTab('today')}
          className={cn(
            'inline-flex h-9 items-center gap-2 rounded px-3 text-sm font-semibold',
            tab === 'today' ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
          )}
        >
          Today
        </button>
        {canSeeMissed ? (
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'missed'}
            onClick={() => setTab('missed')}
            className={cn(
              'inline-flex h-9 items-center gap-2 rounded px-3 text-sm font-semibold',
              tab === 'missed' ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
            )}
          >
            Missed
          </button>
        ) : null}
      </div>

      {tab === 'missed' ? (
        <MissedList />
      ) : isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : error ? (
        <EmptyState title="Could not load checklists" hint={error.message} />
      ) : groups.length === 0 ? (
        <EmptyState title="No checklists today" />
      ) : (
        <div className="flex flex-col gap-4 p-4">
          {groups.map((group) => (
            <section key={group.shift}>
              <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-text3">
                {SHIFT_LABELS[group.shift]}
              </h2>
              <ul className="flex flex-col gap-2">
                {group.rows.map((row) => (
                  <ChecklistCard key={row.id} row={row} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
