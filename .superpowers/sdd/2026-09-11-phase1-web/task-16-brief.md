### Task 16: Work-order board, detail and transitions

**Files:**
- Create: `web/src/features/board/BoardPage.tsx`, `WorkOrderCard.tsx`, `WorkOrderDetailPage.tsx`, `TransitionButtons.tsx`, `transitions.ts`
- Modify: `web/src/routes.tsx` (replace the Board and work-order placeholders)
- Test: `web/src/features/board/transitions.test.ts`, `TransitionButtons.test.tsx`, `BoardPage.test.tsx`, `WorkOrderDetailPage.test.tsx`

**Interfaces:**
- Consumes: `useWorkOrders` / `useWorkOrder` / `usePatchWorkOrder` (Task 15), `useStaff` / `useDepartments` (Task 12), `relativeTime` / `formatClock` / `formatDuration` (Task 10).
- Produces:
  - `transitions.ts`: `TRANSITIONS: Record<WorkOrderStatus, WorkOrderStatus[]>`, `allowedTransitions(from: WorkOrderStatus): WorkOrderStatus[]`, `canTransition(from, to): boolean`, `STATUS_LABELS`, `OPEN_STATUSES`, `BOARD_COLUMNS`
  - `TransitionButtons({ workOrder })`, `WorkOrderCard({ workOrder, assigneeName, departmentName })`, `BoardPage`, `WorkOrderDetailPage`

**`transitions.ts` mirrors `server/app/domain/work_orders.py:41-50` exactly** — this is §7's fourth required web test ("transition button enablement"), and §5.2 says the buttons must "reflect `assert_transition`":

```
open        → assigned, in_progress, cancelled
assigned    → in_progress, open, cancelled
in_progress → blocked, complete, cancelled
blocked     → in_progress, cancelled
complete    → verified, in_progress
verified    → (none)
cancelled   → (none)
```

`OPEN_STATUSES` is `[open, assigned, in_progress, blocked, complete]` — matching the server's, so `verified` and `cancelled` are the closed ones.

**Board layout** (mockup `Board.dc.html`): a header reading `Work orders` with `N active · M urgent`; filter tabs `All`, `Mine`, then one per department, then `Urgent`; a **Board / List** toggle; and a **New** button. Board mode is five columns — `Open`, `Assigned`, `In progress`, `Blocked`, `Complete` — each with a `.col-h` heading (uppercase, 13 px, 700, `border-b-2 border-border2`) carrying its count, holding `.card`s (`bg-surface`, `border-border2`, radius 10, 12 px padding, 8 px gaps). List mode is one table with the same rows.

**Card anatomy:** room or location in mono `roomNum`, priority `Badge` (`urgent`/`high` → `danger`, `normal` → `neutral`, `low` → `neutral` muted), assignee avatar when set, the title on its own line, and a footer of department · age (`relativeTime(createdAt)`) in `text-text3`. Clicking opens `/app/work-orders/<id>`.

**`?mine=1` is honoured on entry** — `landingPath` sends dept_staff and supervisors to `/app/board?mine=1`, so the page reads the query param for its initial filter and keeps the URL in step when the filter changes. Without this, those two roles land on a filter their own landing URL asked for and do not get it.

**Detail screen** (mockup `WorkOrder.dc.html`): back link to the board; `#<id>` in mono; title; room; status and priority badges; a two-column field block (department, assignee, reporter, type, location, opened, completed with elapsed time via `formatDuration`, guest-notified); description with a "Pre-filled from …'s message" line and a link to the source conversation when `sourceConversationId` is set; the resolution text if present; and the `events` timeline newest-first, each entry showing type, actor name, comment and clock time. `TransitionButtons` sits in the header.

**Transition buttons render only reachable statuses**, and only when `can('close_work_order')` for the closing ones (`complete`, `verified`, `cancelled`) — matching the server's capability map so a button never 409s or 403s. `complete` is the primary (amber) action; `cancelled` is the danger variant. Each transition can carry an optional comment, collected in a small dialog for `blocked` and `cancelled` (where "why" is the whole point) and sent as `{ status, comment }`.

- [ ] **Step 1: Write `transitions.ts`**

```ts
import type { Priority, WorkOrderStatus } from '../../api/types'

/** Mirrors server/app/domain/work_orders.py TRANSITIONS. Keep the two in step. */
export const TRANSITIONS: Record<WorkOrderStatus, WorkOrderStatus[]> = {
  open: ['assigned', 'in_progress', 'cancelled'],
  assigned: ['in_progress', 'open', 'cancelled'],
  in_progress: ['blocked', 'complete', 'cancelled'],
  blocked: ['in_progress', 'cancelled'],
  complete: ['verified', 'in_progress'],
  verified: [],
  cancelled: [],
}

export const OPEN_STATUSES: WorkOrderStatus[] = [
  'open',
  'assigned',
  'in_progress',
  'blocked',
  'complete',
]

export const BOARD_COLUMNS = OPEN_STATUSES

export const STATUS_LABELS: Record<WorkOrderStatus, string> = {
  open: 'Open',
  assigned: 'Assigned',
  in_progress: 'In progress',
  blocked: 'Blocked',
  complete: 'Complete',
  verified: 'Verified',
  cancelled: 'Cancelled',
}

/** Closing a work order needs the close_work_order capability on the server. */
export const CLOSING_STATUSES: WorkOrderStatus[] = ['complete', 'verified', 'cancelled']

export function allowedTransitions(from: WorkOrderStatus): WorkOrderStatus[] {
  return TRANSITIONS[from]
}

export function canTransition(from: WorkOrderStatus, to: WorkOrderStatus): boolean {
  return TRANSITIONS[from].includes(to)
}

export const PRIORITY_TONE: Record<Priority, 'neutral' | 'warn' | 'danger'> = {
  low: 'neutral',
  normal: 'neutral',
  high: 'warn',
  urgent: 'danger',
}
```

- [ ] **Step 2: Write the failing transition tests (§7 requirement)**

`web/src/features/board/transitions.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { WorkOrderStatus } from '../../api/types'
import { OPEN_STATUSES, TRANSITIONS, allowedTransitions, canTransition } from './transitions'

const ALL: WorkOrderStatus[] = [
  'open', 'assigned', 'in_progress', 'blocked', 'complete', 'verified', 'cancelled',
]

describe('TRANSITIONS', () => {
  it('matches the server matrix exactly', () => {
    expect(TRANSITIONS).toEqual({
      open: ['assigned', 'in_progress', 'cancelled'],
      assigned: ['in_progress', 'open', 'cancelled'],
      in_progress: ['blocked', 'complete', 'cancelled'],
      blocked: ['in_progress', 'cancelled'],
      complete: ['verified', 'in_progress'],
      verified: [],
      cancelled: [],
    })
  })

  it('covers every status, so a new one cannot be silently unhandled', () => {
    for (const status of ALL) expect(TRANSITIONS[status]).toBeDefined()
  })

  it('treats verified and cancelled as terminal', () => {
    expect(allowedTransitions('verified')).toEqual([])
    expect(allowedTransitions('cancelled')).toEqual([])
  })

  it('lets an open order be assigned, started or cancelled — but not completed', () => {
    expect(canTransition('open', 'assigned')).toBe(true)
    expect(canTransition('open', 'in_progress')).toBe(true)
    expect(canTransition('open', 'cancelled')).toBe(true)
    expect(canTransition('open', 'complete')).toBe(false)
    expect(canTransition('open', 'verified')).toBe(false)
    expect(canTransition('open', 'blocked')).toBe(false)
  })

  it('lets an assigned order go back to open — un-assigning is a real move', () => {
    expect(canTransition('assigned', 'open')).toBe(true)
  })

  it('only allows blocked from in_progress', () => {
    expect(canTransition('in_progress', 'blocked')).toBe(true)
    expect(canTransition('assigned', 'blocked')).toBe(false)
    expect(canTransition('blocked', 'blocked')).toBe(false)
  })

  it('lets a complete order be verified or reopened to in_progress, but never cancelled', () => {
    expect(canTransition('complete', 'verified')).toBe(true)
    expect(canTransition('complete', 'in_progress')).toBe(true)
    expect(canTransition('complete', 'cancelled')).toBe(false)
  })

  it('never allows a self-transition', () => {
    for (const status of ALL) expect(canTransition(status, status)).toBe(false)
  })

  it('lists exactly the five open statuses for the board', () => {
    expect(OPEN_STATUSES).toEqual(['open', 'assigned', 'in_progress', 'blocked', 'complete'])
    expect(OPEN_STATUSES).not.toContain('verified')
    expect(OPEN_STATUSES).not.toContain('cancelled')
  })
})
```

`web/src/features/board/TransitionButtons.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role, WorkOrderStatus } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aWorkOrderDetail } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { TransitionButtons } from './TransitionButtons'

function mount(status: WorkOrderStatus, role: Role = 'dept_staff') {
  return renderWithProviders(
    <SessionProvider>
      <TransitionButtons workOrder={aWorkOrderDetail({ status })} />
    </SessionProvider>,
    { session: sessionFixture({ role }) },
  )
}

describe('TransitionButtons', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(aWorkOrderDetail()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('offers exactly the reachable statuses for an open order', async () => {
    mount('open')
    expect(await screen.findByRole('button', { name: 'Assigned' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'In progress' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelled' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Verified' })).not.toBeInTheDocument()
  })

  it('offers Blocked and Complete only once in progress', async () => {
    mount('in_progress')
    expect(await screen.findByRole('button', { name: 'Blocked' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Complete' })).toBeInTheDocument()
  })

  it('offers Verified and a reopen once complete', async () => {
    mount('complete')
    expect(await screen.findByRole('button', { name: 'Verified' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'In progress' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelled' })).not.toBeInTheDocument()
  })

  it('offers nothing on a verified order', async () => {
    const { container } = mount('verified')
    expect(container.querySelectorAll('button')).toHaveLength(0)
  })

  it('offers nothing on a cancelled order', async () => {
    const { container } = mount('cancelled')
    expect(container.querySelectorAll('button')).toHaveLength(0)
  })

  it('hides the closing transitions from an agent, who lacks close_work_order', async () => {
    mount('in_progress', 'agent')
    expect(await screen.findByRole('button', { name: 'Blocked' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelled' })).not.toBeInTheDocument()
  })

  it('marks Complete as the primary action', async () => {
    mount('in_progress')
    expect((await screen.findByRole('button', { name: 'Complete' })).className).toContain(
      'bg-accent',
    )
  })

  it('patches the status straight through for a plain transition', async () => {
    mount('open')
    await userEvent.click(await screen.findByRole('button', { name: 'In progress' }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ status: 'in_progress' })
  })

  it('asks why before blocking, and sends the comment', async () => {
    mount('in_progress')
    await userEvent.click(await screen.findByRole('button', { name: 'Blocked' }))
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'Waiting on a part')
    await userEvent.click(screen.getByRole('button', { name: /^confirm$/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({
      status: 'blocked',
      comment: 'Waiting on a part',
    })
  })

  it('asks why before cancelling', async () => {
    mount('open')
    await userEvent.click(await screen.findByRole('button', { name: 'Cancelled' }))
    expect(await screen.findByRole('textbox')).toBeInTheDocument()
  })

  it('surfaces a 409 from the server rather than swallowing it', async () => {
    mount('open')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: { code: 'INVALID_TRANSITION', message: 'Cannot move a work order from open to complete' },
        }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await userEvent.click(await screen.findByRole('button', { name: 'In progress' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot move a work order')
  })
})
```

- [ ] **Step 3: Run them to verify they fail**

```bash
cd web && npx vitest run src/features/board
```

Expected: FAIL — neither module resolves.

- [ ] **Step 4: Write `TransitionButtons.tsx`**

```tsx
import { useState } from 'react'
import { usePatchWorkOrder } from '../../api/hooks/workOrders'
import type { WorkOrderDetail, WorkOrderStatus } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, Dialog, Textarea } from '../../components/ui'
import { CLOSING_STATUSES, STATUS_LABELS, allowedTransitions } from './transitions'

/** Blocking or cancelling without a reason is not worth recording. */
const NEEDS_REASON: WorkOrderStatus[] = ['blocked', 'cancelled']

export function TransitionButtons({ workOrder }: { workOrder: WorkOrderDetail }) {
  const { can } = useSession()
  const patch = usePatchWorkOrder(workOrder.id)
  const [asking, setAsking] = useState<WorkOrderStatus | null>(null)
  const [comment, setComment] = useState('')

  const options = allowedTransitions(workOrder.status).filter(
    (status) => !CLOSING_STATUSES.includes(status) || can('close_work_order'),
  )

  function go(status: WorkOrderStatus, withComment?: string) {
    patch.mutate(withComment ? { status, comment: withComment } : { status })
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {patch.error ? (
        <p role="alert" className="w-full rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {patch.error.message}
        </p>
      ) : null}

      {options.map((status) => (
        <Button
          key={status}
          variant={status === 'complete' ? 'primary' : status === 'cancelled' ? 'danger' : 'default'}
          loading={patch.isPending && asking === null}
          onClick={() => (NEEDS_REASON.includes(status) ? setAsking(status) : go(status))}
        >
          {STATUS_LABELS[status]}
        </Button>
      ))}

      <Dialog
        open={asking !== null}
        onClose={() => {
          setAsking(null)
          setComment('')
        }}
        title={asking === 'cancelled' ? 'Cancel work order' : 'Block work order'}
        footer={
          <>
            <Button
              onClick={() => {
                setAsking(null)
                setComment('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={patch.isPending}
              onClick={() => {
                if (!asking) return
                go(asking, comment.trim() || undefined)
                setAsking(null)
                setComment('')
              }}
            >
              Confirm
            </Button>
          </>
        }
      >
        <label className="text-xs font-bold uppercase tracking-widest text-text3" htmlFor="wo-reason">
          Why?
        </label>
        <Textarea
          id="wo-reason"
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      </Dialog>
    </div>
  )
}
```

- [ ] **Step 5: Write `WorkOrderCard.tsx`**

```tsx
import { Link } from 'react-router-dom'
import type { WorkOrderOut } from '../../api/types'
import { Avatar, Badge } from '../../components/ui'
import { relativeTime } from '../../lib/time'
import { PRIORITY_TONE } from './transitions'

export function WorkOrderCard({
  workOrder,
  assigneeName,
  departmentName,
}: {
  workOrder: WorkOrderOut
  assigneeName: string | null
  departmentName: string | null
}) {
  return (
    <Link
      to={`/app/work-orders/${workOrder.id}`}
      className="flex flex-col gap-2 rounded-card border border-border2 bg-surface px-3 pb-2.5 pt-3 hover:border-border3"
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-[13px] font-semibold text-roomNum">
          {workOrder.locationRef ?? '—'}
        </span>
        <Badge tone={PRIORITY_TONE[workOrder.priority]}>{workOrder.priority}</Badge>
        {assigneeName ? (
          <Avatar name={assigneeName} size={22} tone="muted" className="ml-auto" />
        ) : null}
      </div>
      <p className="text-sm font-semibold leading-snug">{workOrder.title}</p>
      <p className="flex items-center gap-2 text-xs text-text3">
        <span>{departmentName ?? 'Unassigned'}</span>
        <span className="font-mono">{relativeTime(workOrder.createdAt)}</span>
      </p>
    </Link>
  )
}
```

`Avatar` needs to accept `className` for the `ml-auto` above — add `className?: string` to its props and pass it through `cn(...)`.

- [ ] **Step 6: Write `BoardPage.tsx`**

```tsx
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
```

- [ ] **Step 7: Write `WorkOrderDetailPage.tsx`**

```tsx
import { Link, useParams } from 'react-router-dom'
import { useWorkOrder } from '../../api/hooks/workOrders'
import { useDepartments, useStaff } from '../../api/hooks/users'
import { Avatar, Badge, EmptyState, Spinner } from '../../components/ui'
import { formatClock, formatDuration } from '../../lib/time'
import { PRIORITY_TONE, STATUS_LABELS } from './transitions'
import { TransitionButtons } from './TransitionButtons'

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-text3">{label}</p>
      <p className="text-sm font-semibold">{value ?? '—'}</p>
    </div>
  )
}

export function WorkOrderDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data, isPending, error } = useWorkOrder(id)
  const { data: staff } = useStaff()
  const { data: departments } = useDepartments()

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !data) return <EmptyState title="Could not load this work order" hint={error?.message} />

  const nameFor = (userId: string | null | undefined) => {
    const person = staff?.find((s) => s.id === userId)
    return person ? `${person.firstName} ${person.lastName}` : null
  }
  const elapsed =
    data.completedAt && data.createdAt
      ? formatDuration((new Date(data.completedAt).getTime() - new Date(data.createdAt).getTime()) / 1000)
      : null

  return (
    <div className="h-full overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <Link to="/app/board" className="text-sm font-semibold text-text3 hover:text-text">
          ← Board
        </Link>
        <span className="font-mono text-sm font-bold text-roomNum">#{data.id}</span>
        <h1 className="text-base font-bold">{data.title}</h1>
        {data.roomNumber ? (
          <span className="font-mono text-lg font-bold text-roomNum">{data.roomNumber}</span>
        ) : null}
        <Badge>{STATUS_LABELS[data.status]}</Badge>
        <Badge tone={PRIORITY_TONE[data.priority]}>{data.priority}</Badge>
        <div className="ml-auto">
          <TransitionButtons workOrder={data} />
        </div>
      </header>

      <div className="grid gap-4 p-4 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">
          <section className="rounded-card border border-border2 bg-surface p-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Department" value={departments?.find((d) => d.id === data.departmentId)?.name} />
              <Field
                label="Assigned to"
                value={
                  nameFor(data.assignedUserId) ? (
                    <span className="flex items-center gap-2">
                      <Avatar name={nameFor(data.assignedUserId)!} size={22} tone="muted" />
                      {nameFor(data.assignedUserId)}
                    </span>
                  ) : (
                    'Unassigned'
                  )
                }
              />
              <Field label="Reported by" value={nameFor(data.reportedByUserId)} />
              <Field label="Type" value={data.type.replace('_', ' ')} />
              <Field label="Location" value={[data.locationType.replace('_', ' '), data.locationRef].filter(Boolean).join(' · ')} />
              <Field label="Opened" value={formatClock(data.createdAt)} />
              <Field
                label="Completed"
                value={data.completedAt ? `${formatClock(data.completedAt)}${elapsed ? ` · ${elapsed}` : ''}` : null}
              />
              <Field label="Guest notified" value={data.guestNotifiedAt ? formatClock(data.guestNotifiedAt) : 'Not yet'} />
            </div>
          </section>

          <section className="rounded-card border border-border2 bg-surface p-4">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-[0.1em] text-text3">Description</h2>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{data.description ?? '—'}</p>
            {data.sourceConversationId ? (
              <p className="mt-3 text-xs text-text3">
                Raised from {data.guestName ?? 'a guest'}&rsquo;s message ·{' '}
                <Link to={`/app/inbox/${data.sourceConversationId}`} className="text-accent hover:underline">
                  open conversation
                </Link>
              </p>
            ) : null}
          </section>
        </div>

        <section className="rounded-card border border-border2 bg-surface p-4">
          <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.1em] text-text3">Timeline</h2>
          {data.events.length === 0 ? (
            <p className="text-xs text-text3">Nothing yet</p>
          ) : (
            <ol className="flex flex-col gap-3">
              {/* Newest first: the last thing that happened is what a reader wants. */}
              {[...data.events].reverse().map((event) => (
                <li key={event.id} className="border-l-2 border-border2 pl-3">
                  <p className="text-[13px] font-semibold">
                    {event.type.replace('_', ' ')}
                    {event.toValue ? ` → ${event.toValue.replace('_', ' ')}` : ''}
                  </p>
                  <p className="text-xs text-text3">
                    {[event.userName, formatClock(event.createdAt)].filter(Boolean).join(' · ')}
                  </p>
                  {event.comment ? <p className="mt-1 text-xs text-text2">{event.comment}</p> : null}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  )
}
```

- [ ] **Step 8: Write the board and detail tests**

`web/src/features/board/BoardPage.test.tsx` — the behaviours worth pinning are the column split, the `?mine=1` honouring, and the urgent filter:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser, aWorkOrder } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { BoardPage } from './BoardPage'

const ORDERS = [
  aWorkOrder({ id: 'w-1', status: 'open', title: 'Faucet dripping', locationRef: '318', priority: 'normal' }),
  aWorkOrder({ id: 'w-2', status: 'assigned', title: 'Toilet running', locationRef: '221', assignedUserId: 'u-eli' }),
  aWorkOrder({ id: 'w-3', status: 'in_progress', title: 'Ice machine', locationRef: '3F', priority: 'urgent' }),
  aWorkOrder({ id: 'w-4', status: 'complete', title: 'AC not cooling', locationRef: '412', priority: 'urgent' }),
]

function serve(orders = ORDERS) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer' })]
        : orders
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
    expect(screen.getByRole('tab', { name: /Mine/ })).toHaveAttribute('aria-selected', 'true')
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

  it('links each card to its detail screen', async () => {
    mount()
    expect(await screen.findByRole('link', { name: /Faucet dripping/ })).toHaveAttribute(
      'href',
      '/app/work-orders/w-1',
    )
  })

  it('shows an empty state when nothing matches', async () => {
    serve([])
    mount()
    expect(await screen.findByText(/nothing on the board/i)).toBeInTheDocument()
  })
})
```

`web/src/features/board/WorkOrderDetailPage.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser, aWorkOrderDetail } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { WorkOrderDetailPage } from './WorkOrderDetailPage'

function serve(detail: unknown) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer' })]
        : detail
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/work-orders/:id" element={<WorkOrderDetailPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'supervisor' }), route: '/app/work-orders/w-204' },
  )
}

describe('WorkOrderDetailPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the id, title, room, status and priority', async () => {
    serve(aWorkOrderDetail({ status: 'complete' }))
    mount()
    expect(await screen.findByText('#w-204')).toBeInTheDocument()
    expect(screen.getByText('AC not cooling')).toBeInTheDocument()
    expect(screen.getByText('412')).toBeInTheDocument()
    expect(screen.getByText('Complete')).toBeInTheDocument()
    expect(screen.getByText('urgent')).toBeInTheDocument()
  })

  it('resolves the department and assignee names', async () => {
    serve(aWorkOrderDetail({ assignedUserId: 'u-eli' }))
    mount()
    expect(await screen.findByText('Engineering')).toBeInTheDocument()
    expect(screen.getByText('Eli Engineer')).toBeInTheDocument()
  })

  it('shows the elapsed time when complete', async () => {
    serve(
      aWorkOrderDetail({
        createdAt: '2026-09-10T18:42:00Z',
        completedAt: '2026-09-10T18:56:00Z',
        status: 'complete',
      }),
    )
    mount()
    expect(await screen.findByText(/14m/)).toBeInTheDocument()
  })

  it('links back to the source conversation', async () => {
    serve(aWorkOrderDetail({ sourceConversationId: 'c-1' }))
    mount()
    expect(await screen.findByRole('link', { name: /open conversation/i })).toHaveAttribute(
      'href',
      '/app/inbox/c-1',
    )
  })

  it('says Not yet when the guest has not been told', async () => {
    serve(aWorkOrderDetail({ guestNotifiedAt: null }))
    mount()
    expect(await screen.findByText('Not yet')).toBeInTheDocument()
  })

  it('renders the timeline newest first', async () => {
    serve(
      aWorkOrderDetail({
        events: [
          { id: 'e1', type: 'created', userId: 'u-ava', userName: 'Ava', fromValue: null, toValue: null, comment: null, createdAt: '2026-09-10T18:42:00Z' },
          { id: 'e2', type: 'status_changed', userId: 'u-eli', userName: 'Eli', fromValue: 'open', toValue: 'in_progress', comment: null, createdAt: '2026-09-10T18:47:00Z' },
        ],
      }),
    )
    mount()
    const items = await screen.findAllByRole('listitem')
    expect(items[0]).toHaveTextContent('status changed')
    expect(items[1]).toHaveTextContent('created')
  })

  it('shows a transition comment in the timeline', async () => {
    serve(
      aWorkOrderDetail({
        events: [
          { id: 'e1', type: 'status_changed', userId: 'u-eli', userName: 'Eli', fromValue: 'in_progress', toValue: 'blocked', comment: 'Waiting on a part', createdAt: '2026-09-10T18:50:00Z' },
        ],
      }),
    )
    mount()
    expect(await screen.findByText('Waiting on a part')).toBeInTheDocument()
  })
})
```

- [ ] **Step 9: Wire the routes**

In `routes.tsx`, replace the `board` and `work-orders/:id` placeholders with `<BoardPage />` and `<WorkOrderDetailPage />`.

- [ ] **Step 10: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 9 transition-matrix tests, 11 button tests, 9 board tests, 7 detail tests.

- [ ] **Step 11: Verify against the real server**

Sign in as `eli@hvh.test` — you land on `/app/board?mine=1` with the **Mine** tab already selected. Switch to **All**: the 15 seeded work orders spread across the five columns. Open one that is `open`: only **Assigned**, **In progress** and **Cancelled** are offered. Move it to **In progress** — **Complete** and **Blocked** appear, **Cancelled** stays. Click **Blocked**, give a reason, and confirm the reason appears in the timeline. Sign in as `ava@hvh.test` and open the same order: **Complete** and **Cancelled** are gone (agents lack `close_work_order`) while **Blocked** remains.

- [ ] **Step 12: Commit**

```bash
git add web/src/features/board web/src/routes.tsx web/src/components/ui/Avatar.tsx
git commit -m "feat(web): work-order board, detail and transitions mirroring assert_transition"
```

---

