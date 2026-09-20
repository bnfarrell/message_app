import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreateUnit, usePatchUnit, useUnits } from '../../api/hooks/pm'
import type { PmUnitKind, UnitOut } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { KindTabs } from '../pm/KindTabs'
import { KIND_LABELS } from '../pm/labels'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'
import { ImportUnitsDialog } from './ImportUnitsDialog'

type Draft = {
  id?: string
  kind: PmUnitKind
  code: string
  name: string
  floor: string
  roomType: string
  externalId: string
  notes: string
  active: boolean
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

function empty(kind: PmUnitKind): Draft {
  return { kind, code: '', name: '', floor: '', roomType: '', externalId: '', notes: '', active: true }
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}

export function UnitsAdmin() {
  const [kind, setKind] = useState<PmUnitKind>('guest_room')
  const { data, isPending, error } = useUnits({ kind })
  const create = useCreateUnit()
  const patch = usePatchUnit()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<UnitOut | null>(null)
  const [importing, setImporting] = useState(false)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)

  const columns: Column<UnitOut>[] = [
    { key: 'code', head: 'Code', mono: true, render: (r) => r.code },
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'floor', head: 'Floor', mono: true, render: (r) => r.floor ?? '—' },
    { key: 'type', head: 'Room type', mono: true, render: (r) => r.roomType ?? '—' },
    { key: 'source', head: 'Source', render: (r) => <Badge>{r.source}</Badge> },
    { key: 'active', head: 'Active', render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>) },
  ]

  function clearFailures() {
    create.reset()
    patch.reset()
  }

  function close() {
    clearFailures()
    setDraft(null)
    setSelected(null)
  }

  function edit(change: Partial<Draft>) {
    if (draft) setDraft({ ...draft, ...change })
  }

  function open(unit: UnitOut) {
    clearFailures()
    setSelected(unit)
    setDraft({
      id: unit.id, kind: unit.kind, code: unit.code, name: unit.name,
      floor: unit.floor === null || unit.floor === undefined ? '' : String(unit.floor),
      roomType: unit.roomType ?? '', externalId: unit.externalId ?? '', notes: unit.notes ?? '',
      active: unit.active,
    })
  }

  function save() {
    if (!draft || !draft.code.trim() || !draft.name.trim()) return
    const body = {
      kind: draft.kind,
      code: draft.code.trim(),
      name: draft.name.trim(),
      floor: draft.floor.trim() === '' ? null : Number(draft.floor),
      roomType: draft.roomType.trim() || null,
      externalId: draft.externalId.trim() || null,
      notes: draft.notes.trim() || null,
    }
    if (draft.id) patch.mutate({ ...body, active: draft.active, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Maintainable units</h1>
          <div className="ml-auto flex gap-2">
            <Button onClick={() => setImporting(true)}>Import CSV</Button>
            <Button
              variant="primary"
              onClick={() => {
                clearFailures()
                setSelected(null)
                setDraft(empty(kind))
              }}
            >
              New unit
            </Button>
          </div>
        </header>
        <KindTabs value={kind} onChange={(next) => next !== 'all' && setKind(next)} />

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load units" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState
              title={`No ${KIND_LABELS[kind].toLowerCase()} yet`}
              hint="Add one, or import the whole inventory from a CSV."
            />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          subjectId={draft.id ?? 'new'}
          title={draft.id ? 'Edit unit' : 'New unit'}
          subtitle={draft.id ? 'Deactivate a retired unit rather than deleting it: its PM history stays attached.' : undefined}
          saving={pending}
          error={failed?.message ?? null}
          onSave={save}
          onCancel={close}
        >
          <div>
            <label className={LABEL} htmlFor="unit-kind">Kind</label>
            <select id="unit-kind" className={SELECT} value={draft.kind}
                    onChange={(e) => edit({ kind: e.target.value as PmUnitKind })}>
              {(Object.keys(KIND_LABELS) as PmUnitKind[]).map((k) => (
                <option key={k} value={k}>{KIND_LABELS[k]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-code">Code</label>
            <Input id="unit-code" value={draft.code} maxLength={40} onChange={(e) => edit({ code: e.target.value })} />
            <FieldError message={fields.code} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-name">Name</label>
            <Input id="unit-name" value={draft.name} maxLength={200} onChange={(e) => edit({ name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-floor">Floor</label>
            <Input id="unit-floor" type="number" value={draft.floor} onChange={(e) => edit({ floor: e.target.value })} />
            <FieldError message={fields.floor} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-room-type">Room type code</label>
            <Input id="unit-room-type" value={draft.roomType} maxLength={20} onChange={(e) => edit({ roomType: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-external-id">PMS id</label>
            <Input id="unit-external-id" value={draft.externalId} maxLength={100} onChange={(e) => edit({ externalId: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-notes">Notes</label>
            <Input id="unit-notes" value={draft.notes} onChange={(e) => edit({ notes: e.target.value })} />
          </div>
          {draft.id ? (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
              Active
            </label>
          ) : null}
        </EditPanel>
      ) : null}

      <ImportUnitsDialog open={importing} onClose={() => setImporting(false)} />
    </div>
  )
}
