import { useMemo, useState } from 'react'
import { useAssignRooms, useHkBoard, useMarkDirty, useSetRush } from '../../api/hooks/housekeeping'
import type { HkRoomOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { RoomDrawer } from './RoomDrawer'
import {
  HK_STATUSES,
  HK_STATUS_LABELS,
  HK_STATUS_TILE,
  OCCUPANCY_GLYPH,
  OCCUPANCY_LABELS,
  initials,
} from './labels'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'
const UNASSIGNED = '__unassigned__'
type Filters = { floor: string; status: string; assignee: string }

function floorKey(room: HkRoomOut): string {
  return room.floor === null || room.floor === undefined ? 'none' : String(room.floor)
}

function floorLabel(key: string): string {
  return key === 'none' ? 'No floor' : `Floor ${key}`
}

function matches(room: HkRoomOut, f: Filters): boolean {
  if (f.floor && floorKey(room) !== f.floor) return false
  if (f.status && room.hkStatus !== f.status) return false
  if (f.assignee === UNASSIGNED) return !room.assignment
  if (f.assignee && room.assignment?.housekeeperUserId !== f.assignee) return false
  return true
}

export function RoomBoardPage() {
  const { can } = useSession()
  const board = useHkBoard()
  const markDirty = useMarkDirty()
  const setRush = useSetRush()
  const assign = useAssignRooms()
  const [filters, setFilters] = useState<Filters>({ floor: '', status: '', assignee: '' })
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openId, setOpenId] = useState<string | null>(null)
  const [keeper, setKeeper] = useState('')
  const [error, setError] = useState<string | null>(null)
  const canManage = can('manage_housekeeping')
  const canSelect = can('mark_room_dirty')

  const rooms = useMemo(() => board.data?.rooms ?? [], [board.data])
  const visible = useMemo(() => rooms.filter((r) => matches(r, filters)), [rooms, filters])
  // The server sorts by floor with floorless units last, so insertion order is display order.
  // Within a floor, rush rooms come first (spec §3.5); sort is stable, so the rest keep order.
  const floors = useMemo(() => {
    const groups = new Map<string, HkRoomOut[]>()
    for (const r of visible) groups.set(floorKey(r), [...(groups.get(floorKey(r)) ?? []), r])
    return [...groups.entries()].map(
      ([key, list]) => [key, [...list].sort((a, b) => Number(b.rush) - Number(a.rush))] as const,
    )
  }, [visible])
  const floorOptions = useMemo(() => [...new Set(rooms.map(floorKey))], [rooms])
  const chosen = rooms.filter((r) => selected.has(r.id))

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      setSelected(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    }
  }

  if (board.isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }
  if (board.error) return <EmptyState title="Could not load the board" hint={board.error.message} />
  const s = board.data.summary

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Rooms</h1>
      </header>
      <dl className="flex flex-wrap gap-4 border-b border-border px-4 py-3 text-sm">
        {([
          ['dirty', 'Dirty', s.dirty],
          ['in-progress', 'In progress', s.inProgress],
          ['awaiting', 'Awaiting inspection', s.awaitingInspection],
          ['inspected', 'Inspected', s.inspected],
          ['ooo', 'Out of order', s.outOfOrder],
        ] as const).map(([key, label, value]) => (
          <div key={key} data-testid={`summary-${key}`} className="flex items-baseline gap-1.5">
            <dt className="text-text3">{label}</dt>
            <dd className="font-mono font-bold">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3 text-xs font-semibold text-text3">
        <label className="flex items-center gap-2">
          Floor
          <select className={SELECT} value={filters.floor}
                  onChange={(e) => setFilters({ ...filters, floor: e.target.value })}>
            <option value="">All</option>
            {floorOptions.map((k) => <option key={k} value={k}>{floorLabel(k)}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Status
          <select className={SELECT} value={filters.status}
                  onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">All</option>
            {HK_STATUSES.map((st) => <option key={st} value={st}>{HK_STATUS_LABELS[st]}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Assignee
          <select className={SELECT} value={filters.assignee}
                  onChange={(e) => setFilters({ ...filters, assignee: e.target.value })}>
            <option value="">Anyone</option>
            <option value={UNASSIGNED}>Unassigned</option>
            {board.data.housekeepers.map((h) => <option key={h.userId} value={h.userId}>{h.name}</option>)}
          </select>
        </label>
      </div>

      {chosen.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface2 px-4 py-2 text-sm">
          <span className="font-semibold">{chosen.length} selected</span>
          {canManage ? (
            <>
              <label className="flex items-center gap-2 text-xs font-semibold text-text3">
                Assign to
                <select className={SELECT} value={keeper} onChange={(e) => setKeeper(e.target.value)}>
                  <option value="">Choose…</option>
                  {board.data.housekeepers.map((h) => (
                    <option key={h.userId} value={h.userId}>{h.name} ({h.assigned})</option>
                  ))}
                </select>
              </label>
              <Button variant="primary" disabled={!keeper} loading={assign.isPending}
                      onClick={() => run(() => assign.mutateAsync({
                        roomIds: chosen.map((r) => r.id) as [string, ...string[]],
                        housekeeperUserId: keeper }))}>
                Assign
              </Button>
            </>
          ) : null}
          <Button onClick={() => run(async () => {
            for (const r of chosen.filter((x) => x.hkStatus === 'inspected')) {
              await markDirty.mutateAsync({ roomId: r.id })
            }
          })}>
            Mark dirty
          </Button>
          <Button onClick={() => run(async () => {
            for (const r of chosen.filter((x) => x.hkStatus === 'dirty' || x.hkStatus === 'in_progress')) {
              await setRush.mutateAsync({ roomId: r.id, on: true })
            }
          })}>
            Rush
          </Button>
          {error ? <span role="alert" className="text-dangerText">{error}</span> : null}
        </div>
      ) : null}

      {floors.length === 0 ? (
        <EmptyState title="No rooms match" />
      ) : (
        floors.map(([key, list]) => (
          <section key={key} className="px-4 py-3">
            <h2 className="mb-2 text-xs font-bold uppercase text-text3">{floorLabel(key)}</h2>
            <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-8">
              {list.map((r) => (
                <li key={r.id}
                    className={cn('relative rounded-card border border-border2 p-2',
                                  HK_STATUS_TILE[r.hkStatus], selected.has(r.id) && 'ring-2 ring-accent')}>
                  {canSelect ? (
                    <input type="checkbox" aria-label={`Select room ${r.code}`} checked={selected.has(r.id)}
                           onChange={() => toggle(r.id)} className="absolute right-2 top-2" />
                  ) : null}
                  <button type="button" onClick={() => setOpenId(r.id)}
                          aria-label={`Room ${r.code}, ${HK_STATUS_LABELS[r.hkStatus]}`}
                          className="flex w-full flex-col items-start text-left">
                    <span className="font-mono text-sm font-bold">{r.code}</span>
                    <span className="text-xs" title={OCCUPANCY_LABELS[r.occupancy]}>
                      {OCCUPANCY_GLYPH[r.occupancy]} {r.rush ? 'RUSH' : ''}
                    </span>
                    <span className="text-xs">{r.assignment ? initials(r.assignment.housekeeperName) : '—'}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
      <RoomDrawer roomId={openId} rooms={rooms} onClose={() => setOpenId(null)} />
    </div>
  )
}
