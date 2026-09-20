import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreatePmTemplate, usePatchPmTemplate, usePmTemplates, useUnits } from '../../api/hooks/pm'
import { useDepartments } from '../../api/hooks/users'
import type {
  PmCadence, PmItemType, PmTemplateMode, PmUnitKind, TemplateItemIn, TemplateOut,
} from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { CADENCE_LABELS, ITEM_TYPE_LABELS, KIND_LABELS } from '../pm/labels'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'
import { RecurrenceBuilder } from './RecurrenceBuilder'

type ItemDraft = {
  id?: string
  label: string
  itemType: PmItemType
  unit: string
  minValue: string
  maxValue: string
  required: boolean
}

type Draft = {
  id?: string
  name: string
  mode: PmTemplateMode
  departmentId: string
  active: boolean
  unitKind: PmUnitKind
  cadence: PmCadence
  rrule: string
  rruleDtstart: string
  unitIds: string[]
  items: ItemDraft[]
  hasRuns: boolean
}

const EMPTY: Draft = {
  name: '', mode: 'sweep', departmentId: '', active: true, unitKind: 'guest_room',
  cadence: 'quarterly', rrule: 'FREQ=MONTHLY', rruleDtstart: '', unitIds: [], items: [],
  hasRuns: false,
}
const NEW_ITEM: ItemDraft = { label: '', itemType: 'checkbox', unit: '', minValue: '', maxValue: '', required: true }

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

function toItemIn(item: ItemDraft): TemplateItemIn {
  const number = item.itemType === 'number'
  return {
    ...(item.id ? { id: item.id } : {}),
    label: item.label.trim(),
    itemType: item.itemType,
    unit: number && item.unit.trim() ? item.unit.trim() : null,
    minValue: number && item.minValue.trim() !== '' ? Number(item.minValue) : null,
    maxValue: number && item.maxValue.trim() !== '' ? Number(item.maxValue) : null,
    required: item.required,
  }
}

function fromTemplate(t: TemplateOut): Draft {
  return {
    id: t.id, name: t.name, mode: t.mode, departmentId: t.departmentId ?? '', active: t.active,
    unitKind: t.unitKind ?? 'guest_room', cadence: t.cadence ?? 'quarterly',
    rrule: t.rrule ?? 'FREQ=MONTHLY', rruleDtstart: t.rruleDtstart ?? '', unitIds: [...(t.unitIds ?? [])],
    hasRuns: t.hasRuns,
    items: (t.items ?? []).map((i) => ({
      id: i.id, label: i.label, itemType: i.itemType, unit: i.unit ?? '',
      minValue: i.minValue === null || i.minValue === undefined ? '' : String(i.minValue),
      maxValue: i.maxValue === null || i.maxValue === undefined ? '' : String(i.maxValue),
      required: i.required,
    })),
  }
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}

export function PmTemplatesAdmin() {
  const { data, isPending, error } = usePmTemplates()
  const { data: departments } = useDepartments()
  const { data: units } = useUnits({ active: true })
  const create = useCreatePmTemplate()
  const patch = usePatchPmTemplate()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<TemplateOut | null>(null)
  const [unitFilter, setUnitFilter] = useState('')

  const rows = data ?? []
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)

  const columns: Column<TemplateOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'mode', head: 'Mode', render: (r) => <Badge>{r.mode === 'sweep' ? 'Sweep' : 'Scheduled'}</Badge> },
    {
      key: 'scope', head: 'Scope',
      render: (r) => r.mode === 'sweep'
        ? `${r.unitKind ? KIND_LABELS[r.unitKind] : ''} · ${r.cadence ? CADENCE_LABELS[r.cadence] : ''}`
        : `${(r.unitIds ?? []).length} unit${(r.unitIds ?? []).length === 1 ? '' : 's'} · ${r.rrule ?? ''}`,
    },
    { key: 'items', head: 'Items', mono: true, render: (r) => (r.items ?? []).length },
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

  function editItem(index: number, change: Partial<ItemDraft>) {
    if (!draft) return
    const items = draft.items.map((item, i) => (i === index ? { ...item, ...change } : item))
    setDraft({ ...draft, items })
  }

  function moveItem(index: number, delta: number) {
    if (!draft) return
    const target = index + delta
    if (target < 0 || target >= draft.items.length) return
    const items = [...draft.items]
    ;[items[index], items[target]] = [items[target]!, items[index]!]
    setDraft({ ...draft, items })
  }

  function open(template: TemplateOut) {
    clearFailures()
    setSelected(template)
    setDraft(fromTemplate(template))
  }

  function save() {
    if (!draft || !draft.name.trim()) return
    const sweep = draft.mode === 'sweep'
    const body = {
      name: draft.name.trim(),
      mode: draft.mode,
      departmentId: draft.departmentId || null,
      active: draft.active,
      unitKind: sweep ? draft.unitKind : null,
      cadence: sweep ? draft.cadence : null,
      rrule: sweep ? null : draft.rrule.trim(),
      rruleDtstart: sweep ? null : draft.rruleDtstart || null,
      unitIds: sweep ? [] : draft.unitIds,
      items: draft.items.map(toItemIn),
    }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  const filteredUnits = (units ?? []).filter((u) => {
    const needle = unitFilter.trim().toLowerCase()
    return !needle || u.code.toLowerCase().includes(needle) || u.name.toLowerCase().includes(needle)
  })

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">PM templates</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              clearFailures()
              setSelected(null)
              setDraft({ ...EMPTY, items: [] })
            }}
          >
            New template
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load templates" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No PM templates" hint="A sweep template covers every unit of a kind on a cadence; a scheduled one raises work orders on a recurrence." />
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
          title={draft.id ? 'Edit template' : 'New template'}
          subtitle={draft.hasRuns ? 'This template has runs: its mode is fixed and removed items are retired, not deleted.' : undefined}
          saving={pending}
          error={failed?.message ?? null}
          onSave={save}
          onCancel={close}
        >
          <div>
            <label className={LABEL} htmlFor="tpl-name">Name</label>
            <Input id="tpl-name" value={draft.name} maxLength={200} onChange={(e) => edit({ name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="tpl-mode">Mode</label>
            <select id="tpl-mode" className={SELECT} value={draft.mode} disabled={draft.hasRuns}
                    onChange={(e) => edit({ mode: e.target.value as PmTemplateMode })}>
              <option value="sweep">Sweep — every unit of a kind, each cycle</option>
              <option value="scheduled">Scheduled — work orders on a recurrence</option>
            </select>
            <FieldError message={fields.mode} />
          </div>
          <div>
            <label className={LABEL} htmlFor="tpl-dept">Department</label>
            <select id="tpl-dept" className={SELECT} value={draft.departmentId}
                    onChange={(e) => edit({ departmentId: e.target.value })}>
              <option value="">None</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          {draft.mode === 'sweep' ? (
            <>
              <div>
                <label className={LABEL} htmlFor="tpl-kind">Unit kind</label>
                <select id="tpl-kind" className={SELECT} value={draft.unitKind}
                        onChange={(e) => edit({ unitKind: e.target.value as PmUnitKind })}>
                  {(Object.keys(KIND_LABELS) as PmUnitKind[]).map((k) => (
                    <option key={k} value={k}>{KIND_LABELS[k]}</option>
                  ))}
                </select>
                <FieldError message={fields.unitKind} />
              </div>
              <div>
                <label className={LABEL} htmlFor="tpl-cadence">Cadence</label>
                <select id="tpl-cadence" className={SELECT} value={draft.cadence}
                        onChange={(e) => edit({ cadence: e.target.value as PmCadence })}>
                  {(Object.keys(CADENCE_LABELS) as PmCadence[]).map((c) => (
                    <option key={c} value={c}>{CADENCE_LABELS[c]}</option>
                  ))}
                </select>
                <FieldError message={fields.cadence} />
              </div>
            </>
          ) : (
            <>
              <RecurrenceBuilder value={draft.rrule} onChange={(rrule) => edit({ rrule })} />
              <FieldError message={fields.rrule} />
              <div>
                <label className={LABEL} htmlFor="tpl-dtstart">Starts on</label>
                <Input id="tpl-dtstart" type="date" value={draft.rruleDtstart}
                       onChange={(e) => edit({ rruleDtstart: e.target.value })} />
                <FieldError message={fields.rruleDtstart} />
              </div>
              <div>
                <p className={LABEL}>Units ({draft.unitIds.length} selected)</p>
                <Input placeholder="Filter units" value={unitFilter} className="mb-2 h-9"
                       onChange={(e) => setUnitFilter(e.target.value)} />
                <ul className="max-h-48 overflow-y-auto rounded border border-border2">
                  {filteredUnits.map((u) => (
                    <li key={u.id}>
                      <label className="flex items-center gap-2 px-2 py-1 text-sm">
                        <input
                          type="checkbox"
                          checked={draft.unitIds.includes(u.id)}
                          onChange={(e) =>
                            edit({
                              unitIds: e.target.checked
                                ? [...draft.unitIds, u.id]
                                : draft.unitIds.filter((id) => id !== u.id),
                            })
                          }
                        />
                        <span className="font-mono text-xs">{u.code}</span> {u.name}
                      </label>
                    </li>
                  ))}
                </ul>
                <FieldError message={fields.unitIds} />
              </div>
            </>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
            Active
          </label>

          <div>
            <div className="mb-1 flex items-center">
              <p className={LABEL}>Checklist</p>
              <Button className="ml-auto" onClick={() => edit({ items: [...draft.items, { ...NEW_ITEM }] })}>
                Add item
              </Button>
            </div>
            <FieldError message={fields.items} />
            <ol className="flex flex-col gap-2">
              {draft.items.map((item, index) => {
                const n = index + 1
                return (
                  <li key={item.id ?? `new-${index}`} className="rounded border border-border2 p-2">
                    <div className="flex flex-col gap-2">
                      <Input aria-label={`Label for item ${n}`} value={item.label} maxLength={200}
                             placeholder="Label" onChange={(e) => editItem(index, { label: e.target.value })} />
                      <div className="flex gap-2">
                        <select aria-label={`Type for item ${n}`} className={SELECT} value={item.itemType}
                                disabled={Boolean(item.id)}
                                onChange={(e) => editItem(index, { itemType: e.target.value as PmItemType })}>
                          {(Object.keys(ITEM_TYPE_LABELS) as PmItemType[]).map((t) => (
                            <option key={t} value={t}>{ITEM_TYPE_LABELS[t]}</option>
                          ))}
                        </select>
                        <label className="flex items-center gap-1 text-xs">
                          <input type="checkbox" checked={item.required}
                                 onChange={(e) => editItem(index, { required: e.target.checked })} />
                          Required
                        </label>
                      </div>
                      {item.itemType === 'number' ? (
                        <div className="flex gap-2">
                          <Input aria-label={`Unit for item ${n}`} placeholder="Unit" className="w-20" maxLength={16}
                                 value={item.unit} onChange={(e) => editItem(index, { unit: e.target.value })} />
                          <Input aria-label={`Min for item ${n}`} type="number" placeholder="Min" step="any"
                                 value={item.minValue} onChange={(e) => editItem(index, { minValue: e.target.value })} />
                          <Input aria-label={`Max for item ${n}`} type="number" placeholder="Max" step="any"
                                 value={item.maxValue} onChange={(e) => editItem(index, { maxValue: e.target.value })} />
                        </div>
                      ) : null}
                      <div className="flex gap-1">
                        <Button variant="ghost" aria-label={`Move item ${n} up`} onClick={() => moveItem(index, -1)}>↑</Button>
                        <Button variant="ghost" aria-label={`Move item ${n} down`} onClick={() => moveItem(index, 1)}>↓</Button>
                        <Button variant="ghost" className="ml-auto text-dangerText" aria-label={`Remove item ${n}`}
                                onClick={() => edit({ items: draft.items.filter((_, i) => i !== index) })}>
                          Remove
                        </Button>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>
        </EditPanel>
      ) : null}
    </div>
  )
}
