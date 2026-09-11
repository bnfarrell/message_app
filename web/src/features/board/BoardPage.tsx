import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useWorkOrders } from '../../api/hooks/workOrders'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { WorkOrderOut } from '../../api/types'
import { Button, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { BOARD_COLUMNS, STATUS_LABELS } from './transitions'
import { WorkOrderCard } from './WorkOrderCard'

export function BoardPage() {
  // landingPath sends dept_staff and supervisors here with ?mine=1 — honour it.
  const [params, setParams] = useSearchParams()
  const mine = params.get('mine') === '1'
  const dept = params.get('dept')
  const urgentOnly = params.get('urgent') === '1'
  const view = params.get('view') === 'list' ? 'list' : 'board'

  const { data, isPending, error } = useWorkOrders({ mine, dept })
  const { data: departments } = useDepartments()
  const { data: staff } = useStaff()

  const rows = useMemo(
    () => (urgentOnly ? (data ?? []).filter((w) => w.priority === 'urgent') : (data ?? [])),
    [data, urgentOnly],
  )
  const urgentCount = (data ?? []).filter((w) => w.priority === 'urgent').length

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value === null) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const nameFor = (id: string | null | undefined) => {
    const person = staff?.find((s) => s.id === id)
    return person ? `${person.firstName} ${person.lastName}` : null
  }
  const deptFor = (id: string | null | undefined) =>
    departments?.find((d) => d.id === id)?.name ?? null

  const tab = (label: string, active: boolean, onClick: () => void, count?: number) => (
    <button
      key={label}
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded px-3.5 text-[13.5px] font-semibold',
        active ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
      )}
    >
      {label}
      {count === undefined ? null : <span className="font-mono text-xs opacity-85">{count}</span>}
    </button>
  )

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error) return <EmptyState title="Could not load the board" hint={error.message} />

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <div>
          <h1 className="text-base font-bold">Work orders</h1>
          <p className="text-xs text-text3">
            {rows.length} active · {urgentCount} urgent
          </p>
        </div>
        <div role="tablist" className="ml-4 flex flex-wrap gap-1.5">
          {tab('All', !mine && !dept && !urgentOnly, () => setParams(new URLSearchParams(), { replace: true }), data?.length)}
          {tab('Mine', mine, () => setParam('mine', mine ? null : '1'))}
          {(departments ?? []).map((department) =>
            tab(department.name, dept === department.id, () =>
              setParam('dept', dept === department.id ? null : department.id),
            ),
          )}
          {tab('Urgent', urgentOnly, () => setParam('urgent', urgentOnly ? null : '1'), urgentCount)}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button onClick={() => setParam('view', view === 'board' ? 'list' : 'board')}>
            {view === 'board' ? 'List' : 'Board'}
          </Button>
        </div>
      </header>

      {rows.length === 0 ? (
        <EmptyState title="Nothing on the board" hint="No work orders match this filter." />
      ) : view === 'board' ? (
        <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto p-4">
          {BOARD_COLUMNS.map((status) => {
            const column = rows.filter((w) => w.status === status)
            return (
              <div key={status} className="flex min-w-[240px] flex-1 flex-col gap-2.5">
                <h2 className="flex items-center gap-2 border-b-2 border-border2 pb-1.5 text-[13px] font-bold uppercase tracking-wider text-text2">
                  {STATUS_LABELS[status]}
                  <span className="font-mono text-xs text-text3">{column.length}</span>
                </h2>
                {column.map((workOrder: WorkOrderOut) => (
                  <WorkOrderCard
                    key={workOrder.id}
                    workOrder={workOrder}
                    assigneeName={nameFor(workOrder.assignedUserId)}
                    departmentName={deptFor(workOrder.departmentId)}
                  />
                ))}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="flex flex-col gap-2">
            {rows.map((workOrder) => (
              <WorkOrderCard
                key={workOrder.id}
                workOrder={workOrder}
                assigneeName={nameFor(workOrder.assignedUserId)}
                departmentName={deptFor(workOrder.departmentId)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
