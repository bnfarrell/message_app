import { useState } from 'react'
import {
  useCompleteAssignment,
  useMyRooms,
  useStartAssignment,
  useUploadHkPhoto,
} from '../../api/hooks/housekeeping'
import type { HkRoomOut } from '../../api/types'
import { Badge, Button, EmptyState, Spinner } from '../../components/ui'
import { SERVICE_LABELS } from './labels'

const BIG = 'h-12 min-w-32 text-base'

/** The one big button (docs/design.md §6.5): whatever the room needs next, nothing else. */
function NextAction({ room }: { room: HkRoomOut }) {
  const start = useStartAssignment()
  const complete = useCompleteAssignment()
  const a = room.assignment!
  if (a.status === 'assigned') {
    return (
      <div className="flex flex-col items-end gap-1">
        <Button variant="primary" className={BIG} loading={start.isPending}
                onClick={() => start.mutate(a.id)}>Start</Button>
        {start.error ? <p role="alert" className="text-sm text-dangerText">{start.error.message}</p> : null}
      </div>
    )
  }
  if (a.status === 'in_progress') {
    return (
      <div className="flex flex-col items-end gap-1">
        <Button variant="primary" className={BIG} loading={complete.isPending}
                onClick={() => complete.mutate(a.id)}>Mark ready</Button>
        {complete.error ? <p role="alert" className="text-sm text-dangerText">{complete.error.message}</p> : null}
      </div>
    )
  }
  return <Badge tone={a.status === 'passed' ? 'ok' : 'note'}>{a.status === 'passed' ? 'Inspected' : 'Ready'}</Badge>
}

function sentBack(room: HkRoomOut): string | null {
  const a = room.assignment
  if (!a || a.failCount === 0 || !a.inspectionNote) return null
  return a.status === 'assigned' || a.status === 'in_progress' ? a.inspectionNote : null
}

function RoomScreen({ room, onBack }: { room: HkRoomOut; onBack: () => void }) {
  const upload = useUploadHkPhoto()
  const a = room.assignment!
  const note = sentBack(room)
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <Button variant="ghost" className="self-start" onClick={onBack}>Back to my rooms</Button>
      <h1 className="font-mono text-3xl font-bold text-roomNum">{room.code}</h1>
      <p className="text-sm text-text3">
        {[room.roomType, SERVICE_LABELS[a.type]].filter(Boolean).join(' · ')}
      </p>
      {note ? (
        <p role="note" className="rounded-card bg-dangerBg p-3 text-sm text-dangerText">
          Sent back: {note}
        </p>
      ) : null}
      <NextAction room={room} />
      {a.status === 'in_progress' ? (
        <label className="flex flex-col gap-1 text-sm font-semibold">
          Add photo
          <input type="file" accept="image/*" capture="environment"
                 onChange={(e) => {
                   const file = e.target.files?.[0]
                   if (file) upload.mutate({ assignmentId: a.id, file })
                 }} />
        </label>
      ) : null}
      {upload.error ? <p role="alert" className="text-sm text-dangerText">{upload.error.message}</p> : null}
    </div>
  )
}

export function MyRoomsPage() {
  const mine = useMyRooms()
  const [openId, setOpenId] = useState<string | null>(null)
  if (mine.isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }
  if (mine.error) return <EmptyState title="Could not load your rooms" hint={mine.error.message} />
  const rows = mine.data
  const open = rows.find((r) => r.id === openId)
  if (open) return <RoomScreen room={open} onBack={() => setOpenId(null)} />
  const done = rows.filter((r) => r.assignment?.status === 'done' || r.assignment?.status === 'passed').length

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">My Rooms</h1>
        <p className="text-sm text-text3">{done} of {rows.length} done</p>
      </header>
      {rows.length === 0 ? (
        <EmptyState title="No rooms assigned to you today" />
      ) : (
        <ul className="flex flex-col gap-2 p-4">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center gap-3 rounded-card border border-border2 bg-surface p-3">
              <button type="button" aria-label={`Open room ${r.code}`} onClick={() => setOpenId(r.id)}
                      className="flex flex-1 flex-col text-left">
                <span className="flex items-center gap-2">
                  <span className="font-mono text-lg font-bold text-roomNum">{r.code}</span>
                  {r.rush ? <Badge tone="danger">Rush</Badge> : null}
                  {sentBack(r) ? <Badge tone="warn">Sent back</Badge> : null}
                </span>
                <span className="text-xs text-text3">
                  {[r.roomType, r.assignment ? SERVICE_LABELS[r.assignment.type] : null].filter(Boolean).join(' · ')}
                </span>
              </button>
              <NextAction room={r} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
