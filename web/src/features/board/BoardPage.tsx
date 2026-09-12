import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useWorkOrders } from '../../api/hooks/workOrders'
import { useDepartments, useStaff } from '../../api/hooks/users'
import { useSession } from '../../auth/SessionContext'
import type { WorkOrderOut } from '../../api/types'
import { Button, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { useMediaQuery } from '../../lib/useMediaQuery'
import { CreateWorkOrderModal } from '../inbox/CreateWorkOrderModal'
import { BOARD_COLUMNS, CLOSED_STATUSES, OPEN_STATUSES, STATUS_LABELS } from './transitions'
import { WorkOrderCard } from './WorkOrderCard'

type Filter = { kind: 'all' } | { kind: 'mine' } | { kind: 'dept'; id: string } | { kind: 'urgent' }

/** The filter row is single-select: Board.dc.html draws five `.tab`s with exactly one `.on`.
 *
 * The three params stay separate rather than collapsing into one, so landingPath's `?mine=1`
 * entry and every link already in the wild keep working. A URL that still carries two of them
 * resolves to a single winner here instead of lighting two tabs. */
function selectedFilter(params: URLSearchParams): Filter {
  if (params.get('mine') === '1') return { kind: 'mine' }
  const dept = params.get('dept')
  if (dept) return { kind: 'dept', id: dept }
  if (params.get('urgent') === '1') return { kind: 'urgent' }
  return { kind: 'all' }
}

export function BoardPage() {
  // landingPath sends dept_staff and supervisors here with ?mine=1 — honour it.
  const [params, setParams] = useSearchParams()
  const { can } = useSession()
  const isMobile = useMediaQuery('(max-width: 767px)')
  const [creating, setCreating] = useState(false)
  const selected = selectedFilter(params)
  const urgentOnly = selected.kind === 'urgent'
  // The kanban board's columns scroll horizontally, which has no good affordance on a phone,
  // so a narrow viewport defaults to the (already existing) list view — but only as a
  // default: an explicit ?view= in the URL, from either toggle, still wins.
  const viewParam = params.get('view')
  const view =
    viewParam === 'list' || viewParam === 'board' ? viewParam : isMobile ? 'list' : 'board'
  // Verified and cancelled are left out of the list entirely unless asked for, so revealing
  // them is a refetch, not a client-side filter. In the URL so the reveal survives a reload.
  const showClosed = params.get('closed') === '1'

  const { data, isPending, error } = useWorkOrders({
    mine: selected.kind === 'mine',
    dept: selected.kind === 'dept' ? selected.id : null,
    includeClosed: showClosed,
  })
  const { data: departments } = useDepartments()
  const { data: staff } = useStaff()

  const rows = useMemo(
    () => (urgentOnly ? (data ?? []).filter((w) => w.priority === 'urgent') : (data ?? [])),
    [data, urgentOnly],
  )
  const active = rows.filter((w) => OPEN_STATUSES.includes(w.status))
  const closed = rows.filter((w) => CLOSED_STATUSES.includes(w.status))
  const urgentCount = (data ?? []).filter(
    (w) => w.priority === 'urgent' && OPEN_STATUSES.includes(w.status),
  ).length
  const columns = showClosed ? [...BOARD_COLUMNS, ...CLOSED_STATUSES] : BOARD_COLUMNS

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value === null) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  // Picking a tab clears the other two, so only one is ever lit. `select({})` is the "All" tab.
  // It touches the filters only: resetting the whole query string also dropped view=list,
  // silently throwing the user back to the board they had switched away from.
  function select(filter: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const key of ['mine', 'dept', 'urgent']) next.delete(key)
    for (const [key, value] of Object.entries(filter)) next.set(key, value)
    setParams(next, { replace: true })
  }

  const nameFor = (id: string | null | undefined) => {
    const person = staff?.find((s) => s.id === id)
    return person ? `${person.firstName} ${person.lastName}` : null
  }
  const deptFor = (id: string | null | undefined) =>
    departments?.find((d) => d.id === id)?.name ?? null

  const card = (workOrder: WorkOrderOut) => (
    <WorkOrderCard
      key={workOrder.id}
      workOrder={workOrder}
      assigneeName={nameFor(workOrder.assignedUserId)}
      departmentName={deptFor(workOrder.departmentId)}
    />
  )

  const tab = (label: string, active: boolean, onClick: () => void, count?: number) => (
    <button
      key={label}
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'inline-flex h-11 items-center gap-2 rounded px-3.5 text-[13.5px] font-semibold md:h-9',
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
            {active.length} active · {urgentCount} urgent
          </p>
        </div>
        <div role="tablist" className="ml-4 flex flex-wrap gap-1.5">
          {tab('All', selected.kind === 'all', () => select({}), data?.length)}
          {tab('Mine', selected.kind === 'mine', () => select({ mine: '1' }))}
          {(departments ?? []).map((department) =>
            tab(
              department.name,
              selected.kind === 'dept' && selected.id === department.id,
              () => select({ dept: department.id }),
            ),
          )}
          {tab('Urgent', urgentOnly, () => select({ urgent: '1' }), urgentCount)}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button onClick={() => setParam('view', view === 'board' ? 'list' : 'board')}>
            {view === 'board' ? 'List' : 'Board'}
          </Button>
          {/* Board.dc.html:69. Plenty of the mockup's work orders — POOL PUMP, 3F ICE, ELEV B —
              have no guest conversation behind them, and none of them could be raised at all. */}
          {can('create_work_order') ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              New
            </Button>
          ) : null}
        </div>
      </header>

      {rows.length === 0 ? (
        <div className="flex-1">
          <EmptyState title="Nothing on the board" hint="No work orders match this filter." />
        </div>
      ) : view === 'board' ? (
        <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto p-4">
          {columns.map((status) => {
            const column = rows.filter((w) => w.status === status)
            return (
              <div key={status} className="flex min-w-[240px] flex-1 flex-col gap-2.5">
                <h2 className="flex items-center gap-2 border-b-2 border-border2 pb-1.5 text-[13px] font-bold uppercase tracking-wider text-text2">
                  {STATUS_LABELS[status]}
                  <span className="font-mono text-xs text-text3">{column.length}</span>
                </h2>
                {column.map(card)}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="flex flex-col gap-2">{active.map(card)}</div>
          {/* The card carries no status, so closed work cannot simply be mixed into the list:
              it gets one group per terminal state, the same split the board columns make. */}
          {CLOSED_STATUSES.map((status) => {
            const group = closed.filter((w) => w.status === status)
            if (group.length === 0) return null
            return (
              <section key={status} className="mt-5 flex flex-col gap-2">
                <h2 className="flex items-center gap-2 border-b-2 border-border2 pb-1.5 text-[13px] font-bold uppercase tracking-wider text-text2">
                  {STATUS_LABELS[status]}
                  <span className="font-mono text-xs text-text3">{group.length}</span>
                </h2>
                {group.map(card)}
              </section>
            )
          })}
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-1.5 border-t border-border px-4 py-2 text-xs text-text3">
        {showClosed ? (
          <>
            <span>
              Showing <span className="font-mono">{closed.length}</span> verified and cancelled
            </span>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              onClick={() => setParam('closed', null)}
              className="rounded font-semibold text-accent hover:underline"
            >
              hide them
            </button>
          </>
        ) : (
          <>
            <span>Verified and cancelled hidden</span>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              onClick={() => setParam('closed', '1')}
              className="rounded font-semibold text-accent hover:underline"
            >
              show closed
            </button>
          </>
        )}
      </footer>

      {/* Mounted only while open: the modal needs a ToastProvider, the same reason the
          composer mounts it this way. */}
      {creating ? <CreateWorkOrderModal open onClose={() => setCreating(false)} /> : null}
    </div>
  )
}
