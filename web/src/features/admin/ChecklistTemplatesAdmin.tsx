import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreateChecklistTemplate, usePatchChecklistTemplate, useChecklistTemplates } from '../../api/hooks/checklists'
import { useDepartments } from '../../api/hooks/users'
import type { ChecklistSchedule, ChecklistTemplateIn, ChecklistTemplateOut, Shift } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { SHIFT_LABELS, WEEKDAYS, weekdayLabel } from '../checklists/labels'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'
import { FieldError, ItemListEditor, itemDraftFrom, toItemIn, type ItemDraft } from './ItemListEditor'

type Draft = {
  id?: string
  name: string
  departmentId: string
  schedule: ChecklistSchedule
  shift: Shift
  days: boolean[]
  active: boolean
  items: ItemDraft[]
}

const EMPTY: Draft = {
  name: '', departmentId: '', schedule: 'weekly', shift: 'am',
  days: [true, true, true, true, true, true, true], active: true, items: [],
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

function fromTemplate(t: ChecklistTemplateOut): Draft {
  const mask = t.weekdays ?? 0
  return {
    id: t.id, name: t.name, departmentId: t.departmentId ?? '', schedule: t.schedule,
    shift: t.shift ?? 'am',
    days: WEEKDAYS.map((_, i) => Boolean((mask >> i) & 1)),
    active: t.active,
    items: (t.items ?? []).map(itemDraftFrom),
  }
}

export function ChecklistTemplatesAdmin() {
  const { data, isPending, error } = useChecklistTemplates()
  const { data: departments } = useDepartments()
  const create = useCreateChecklistTemplate()
  const patch = usePatchChecklistTemplate()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<ChecklistTemplateOut | null>(null)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)

  const columns: Column<ChecklistTemplateOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'department', head: 'Department', render: (r) => r.departmentName ?? '' },
    {
      key: 'schedule', head: 'Schedule',
      render: (r) => r.schedule === 'on_demand'
        ? 'On demand'
        : `${r.shift ? SHIFT_LABELS[r.shift] : ''} · ${weekdayLabel(r.weekdays)}`,
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

  function open(template: ChecklistTemplateOut) {
    clearFailures()
    setSelected(template)
    setDraft(fromTemplate(template))
  }

  function save() {
    if (!draft || !draft.name.trim()) return
    const weekly = draft.schedule === 'weekly'
    const body: ChecklistTemplateIn = {
      name: draft.name.trim(), departmentId: draft.departmentId, schedule: draft.schedule,
      shift: weekly ? draft.shift : null,
      weekdays: weekly
        ? draft.days.reduce((mask, on, i) => (on ? mask | (1 << i) : mask), 0) : null,
      // Items1 is a non-empty tuple; the server itself enforces "at least one item"
      // (ValidationFailed on save), so a cast here is safe and mirrors that contract.
      active: draft.active, items: draft.items.map(toItemIn) as ChecklistTemplateIn['items'],
    }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Checklist templates</h1>
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
            <EmptyState title="No checklist templates" hint="A weekly template repeats on a shift and chosen days; an on-demand one is started manually." />
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
            <label className={LABEL} htmlFor="tpl-dept">Department</label>
            <select id="tpl-dept" aria-label="Department" className={SELECT} value={draft.departmentId}
                    onChange={(e) => edit({ departmentId: e.target.value })}>
              <option value="">None</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <FieldError message={fields.departmentId} />
          </div>

          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="schedule" checked={draft.schedule === 'weekly'}
                     onChange={() => edit({ schedule: 'weekly' })} />
              Weekly
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="schedule" checked={draft.schedule === 'on_demand'}
                     onChange={() => edit({ schedule: 'on_demand' })} />
              On demand
            </label>
          </div>

          {draft.schedule === 'weekly' ? (
            <>
              <div>
                <label className={LABEL} htmlFor="tpl-shift">Shift</label>
                <select id="tpl-shift" aria-label="Shift" className={SELECT} value={draft.shift}
                        onChange={(e) => edit({ shift: e.target.value as Shift })}>
                  {(Object.keys(SHIFT_LABELS) as Shift[]).map((s) => (
                    <option key={s} value={s}>{SHIFT_LABELS[s]}</option>
                  ))}
                </select>
                <FieldError message={fields.shift} />
              </div>
              <div>
                <p className={LABEL}>Days</p>
                <div className="flex flex-wrap gap-3">
                  {WEEKDAYS.map((day, i) => (
                    <label key={day} className="flex items-center gap-1 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.days[i]}
                        onChange={(e) =>
                          edit({ days: draft.days.map((d, j) => (j === i ? e.target.checked : d)) })
                        }
                      />
                      {day}
                    </label>
                  ))}
                </div>
                <FieldError message={fields.weekdays} />
              </div>
            </>
          ) : null}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
            Active
          </label>

          <ItemListEditor items={draft.items} onChange={(items) => edit({ items })} error={fields.items} />
        </EditPanel>
      ) : null}
    </div>
  )
}
