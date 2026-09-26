import { useState } from 'react'
import { useHkInspections, useInspectRoom } from '../../api/hooks/housekeeping'
import type { HkInspectionRowOut } from '../../api/types'
import { Button, Dialog, EmptyState, Spinner, Textarea } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { SERVICE_LABELS } from './labels'

/** Mirrors PM's InspectionPage so supervisors meet one pattern twice (spec §4.3). */
export function RoomInspectionPage() {
  const queue = useHkInspections()
  const inspect = useInspectRoom()
  const [failing, setFailing] = useState<HkInspectionRowOut | null>(null)
  const [note, setNote] = useState('')

  function close() {
    setFailing(null)
    setNote('')
  }

  if (queue.isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }
  if (queue.error) return <EmptyState title="Could not load the queue" hint={queue.error.message} />

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Room Inspection</h1>
      </header>
      {inspect.error && !failing ? (
        <p role="alert" className="mx-4 mt-3 text-sm text-dangerText">{inspect.error.message}</p>
      ) : null}
      {queue.data.length === 0 ? (
        <EmptyState title="No rooms are waiting for inspection" />
      ) : (
        <ul className="flex flex-col gap-2 p-4">
          {queue.data.map((row) => {
            const a = row.room.assignment!
            return (
              <li key={row.room.id} className="flex flex-wrap items-center gap-3 rounded-card border border-border2 bg-surface p-3">
                <span className="font-mono text-sm font-bold text-roomNum">{row.room.code}</span>
                <span className="text-xs text-text3">
                  {SERVICE_LABELS[a.type]} · {a.housekeeperName ?? 'Unknown'}
                  {a.completedAt ? ` · ${formatClock(a.completedAt)}` : ''}
                  {a.failCount > 0 ? ` · failed ${a.failCount}× before` : ''}
                </span>
                <span className="flex gap-1">
                  {row.photos.map((p) => (
                    <img key={p.id} src={p.url} alt={`Photo of room ${row.room.code}`}
                         className="h-12 w-12 rounded object-cover" />
                  ))}
                </span>
                <span className="ml-auto flex gap-2">
                  <Button variant="primary" aria-label={`Pass room ${row.room.code}`}
                          loading={inspect.isPending}
                          onClick={() => inspect.mutate({ assignmentId: a.id, result: 'pass' })}>
                    Pass
                  </Button>
                  <Button variant="danger" aria-label={`Fail room ${row.room.code}`}
                          onClick={() => setFailing(row)}>
                    Fail
                  </Button>
                </span>
              </li>
            )
          })}
        </ul>
      )}
      <Dialog
        open={failing !== null}
        onClose={close}
        title={failing ? `Fail room ${failing.room.code}` : 'Fail room'}
        footer={
          <>
            <Button onClick={close}>Cancel</Button>
            <Button variant="danger" disabled={!note.trim()} loading={inspect.isPending}
                    onClick={() => {
                      if (!failing) return
                      inspect.mutate(
                        { assignmentId: failing.room.assignment!.id, result: 'fail', note: note.trim() },
                        { onSuccess: close },
                      )
                    }}>
              Fail room
            </Button>
          </>
        }
      >
        <label className="flex flex-col gap-1 text-sm font-semibold">
          What needs fixing?
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
        </label>
        {inspect.error && failing ? (
          <p role="alert" className="text-sm text-dangerText">{inspect.error.message}</p>
        ) : null}
      </Dialog>
    </div>
  )
}
