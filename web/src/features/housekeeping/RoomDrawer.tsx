import {
  useHkRoom,
  useReorder,
  useSelfAssignStart,
  useSetRoomStatus,
  useSetRush,
  useUnassign,
} from '../../api/hooks/housekeeping'
import type { HkAssignmentOut, HkRoomOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Badge, Button, Dialog, Spinner } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { EVENT_LABELS, HK_STATUS_LABELS, OCCUPANCY_LABELS, SERVICE_LABELS } from './labels'

function queueOf(rooms: HkRoomOut[], a: HkAssignmentOut): HkAssignmentOut[] {
  return rooms
    .map((r) => r.assignment)
    .filter((x): x is HkAssignmentOut =>
      !!x && x.housekeeperUserId === a.housekeeperUserId && x.shiftDate === a.shiftDate &&
      x.status !== 'passed')
    .sort((x, y) => x.sequence - y.sequence)
}

export function RoomDrawer({
  roomId,
  rooms,
  onClose,
}: {
  roomId: string | null
  rooms: HkRoomOut[]
  onClose: () => void
}) {
  const { can } = useSession()
  const detail = useHkRoom(roomId)
  const setStatus = useSetRoomStatus()
  const unassign = useUnassign()
  const reorder = useReorder()
  const selfStart = useSelfAssignStart()
  const setRush = useSetRush()
  const room = detail.data?.room
  const a = room?.assignment ?? null
  const canManage = can('manage_housekeeping')
  const out = room?.hkStatus === 'out_of_order' || room?.hkStatus === 'out_of_service'
  const error = setStatus.error ?? unassign.error ?? reorder.error ?? selfStart.error
    ?? setRush.error

  function move(delta: -1 | 1) {
    if (!a) return
    const ids = queueOf(rooms, a).map((x) => x.id)
    const i = ids.indexOf(a.id)
    const j = i + delta
    if (i < 0 || j < 0 || j >= ids.length) return
    const next = [...ids]
    const held = next[i]!
    next[i] = next[j]!
    next[j] = held
    reorder.mutate({
      housekeeperUserId: a.housekeeperUserId,
      assignmentIds: next as [string, ...string[]],
    })
  }

  return (
    <Dialog open={roomId !== null} onClose={onClose} title={room ? `Room ${room.code}` : 'Room'} wide>
      {!room ? (
        <div className="flex justify-center py-6">
          <Spinner />
        </div>
      ) : (
        <div className="flex flex-col gap-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{HK_STATUS_LABELS[room.hkStatus]}</Badge>
            {room.serviceType ? <Badge tone="note">{SERVICE_LABELS[room.serviceType]}</Badge> : null}
            {room.rush ? <Badge tone="danger">Rush</Badge> : null}
          </div>
          <p>
            {OCCUPANCY_LABELS[room.occupancy]}
            {room.guestName ? ` · ${room.guestName}` : ''}
            {room.departureDate ? ` · departs ${room.departureDate}` : ''}
          </p>
          {a ? (
            <section aria-label="Assignment">
              <p>
                {a.housekeeperName ?? 'Unknown'} · {a.status.replace('_', ' ')}
                {a.failCount > 0 ? ` · failed ${a.failCount}×` : ''}
              </p>
              {a.inspectionNote ? <p className="text-text3">“{a.inspectionNote}”</p> : null}
            </section>
          ) : (
            <p className="text-text3">Not assigned today</p>
          )}
          {detail.data!.photos.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {detail.data!.photos.map((p) => (
                <img key={p.id} src={p.url} alt={`Photo from ${formatClock(p.createdAt)}`}
                     className="h-24 w-24 rounded object-cover" />
              ))}
            </div>
          ) : null}
          {canManage ? (
            <div className="flex flex-wrap gap-2">
              {room.hkStatus !== 'out_of_order' ? (
                <Button onClick={() => setStatus.mutate({ roomId: room.id, status: 'out_of_order' })}>
                  Out of order
                </Button>
              ) : null}
              {room.hkStatus !== 'out_of_service' ? (
                <Button onClick={() => setStatus.mutate({ roomId: room.id, status: 'out_of_service' })}>
                  Out of service
                </Button>
              ) : null}
              {out ? (
                <Button onClick={() => setStatus.mutate({ roomId: room.id, status: 'dirty' })}>
                  Back in service
                </Button>
              ) : null}
              {/* Supervisors clean rooms too (spec §3.3); it then appears in their My Rooms. */}
              {room.hkStatus === 'dirty' && !a ? (
                <Button onClick={() => selfStart.mutate(room.id)}>Clean it myself</Button>
              ) : null}
              {a && a.status === 'assigned' ? (
                <>
                  <Button onClick={() => unassign.mutate(a.id)}>Unassign</Button>
                  <Button onClick={() => move(-1)}>Move earlier</Button>
                  <Button onClick={() => move(1)}>Move later</Button>
                </>
              ) : null}
            </div>
          ) : null}
          {room.rush && can('mark_room_dirty') ? (
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => setRush.mutate({ roomId: room.id, on: false })}>
                Clear rush
              </Button>
            </div>
          ) : null}
          {error ? <p role="alert" className="text-sm text-dangerText">{error.message}</p> : null}
          <section aria-label="History">
            <h3 className="mb-1 text-xs font-bold uppercase text-text3">History</h3>
            <ol className="flex flex-col gap-1">
              {detail.data!.events.map((e) => (
                <li key={e.id} className="text-xs">
                  <span className="font-semibold">{EVENT_LABELS[e.type]}</span>
                  {e.toValue ? ` → ${e.toValue}` : ''}
                  {' · '}
                  {e.userName ?? 'System'} · {formatClock(e.createdAt)}
                  {e.comment ? <span className="text-text3"> — {e.comment}</span> : null}
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </Dialog>
  )
}
