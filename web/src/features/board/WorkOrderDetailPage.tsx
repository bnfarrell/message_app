import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useWorkOrder } from '../../api/hooks/workOrders'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { WorkOrderEventOut } from '../../api/types'
import { Avatar, Badge, EmptyState, Spinner } from '../../components/ui'
import { formatClock, formatDuration } from '../../lib/time'
import { CommentBox } from './CommentBox'
import { PhotoPanel } from './PhotoPanel'
import { PRIORITY_TONE, STATUS_LABELS } from './transitions'
import { TransitionButtons } from './TransitionButtons'

/** Every other event type reads as "type → toValue"; photo_attached reads more naturally as
 * "before/after photo attached", matching the mockup's "Eli · after photo attached · 18:56". */
function eventTitle(event: WorkOrderEventOut): string {
  if (event.type === 'photo_attached') return `${event.toValue ?? ''} photo attached`.trim()
  return `${event.type.replace('_', ' ')}${event.toValue ? ` → ${event.toValue.replace('_', ' ')}` : ''}`
}

function Field({ label, value }: { label: string; value: ReactNode }) {
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
            {data.pmRunId ? (
              <p className="mt-3 text-xs text-text3">
                Scheduled preventative maintenance ·{' '}
                <Link to={`/app/pm/runs/${data.pmRunId}`} className="text-accent hover:underline">
                  Open PM checklist
                </Link>
              </p>
            ) : null}
          </section>

          <PhotoPanel workOrderId={data.id} photos={data.photos} />
        </div>

        <div className="flex flex-col gap-4">
          <section className="rounded-card border border-border2 bg-surface p-4">
            <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.1em] text-text3">Timeline</h2>
            {data.events.length === 0 ? (
              <p className="text-xs text-text3">Nothing yet</p>
            ) : (
              <ol className="flex flex-col gap-3">
                {/* Newest first: the last thing that happened is what a reader wants. */}
                {[...data.events].reverse().map((event) => (
                  <li key={event.id} className="border-l-2 border-border2 pl-3">
                    <p className="text-[13px] font-semibold">{eventTitle(event)}</p>
                    <p className="text-xs text-text3">
                      {[event.userName, formatClock(event.createdAt)].filter(Boolean).join(' · ')}
                    </p>
                    {event.comment ? (
                      <p className="mt-1 text-xs text-text2">{event.comment}</p>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
          </section>

          <CommentBox workOrderId={data.id} />
        </div>
      </div>
    </div>
  )
}
