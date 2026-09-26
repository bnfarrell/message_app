import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useAdminLogTemplates, useCreateLogTemplate, usePatchLogTemplate } from '../../api/hooks/log'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { LogFieldType, LogTemplateIn, LogTemplateOut, Shift } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { SHIFT_LABELS } from '../checklists/labels'
import { FIELD_TYPE_LABELS, audienceSummary } from '../log/templates'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'
import { FieldError, LABEL, SELECT } from './ItemListEditor'

type FieldDraft = { id?: string; label: string; fieldType: LogFieldType; required: boolean }

type Draft = {
  id?: string
  name: string
  shift: Shift | ''
  active: boolean
  fields: FieldDraft[]
  departmentIds: string[]
  userIds: string[]
}

const EMPTY: Draft = { name: '', shift: '', active: true, fields: [], departmentIds: [], userIds: [] }
const NEW_FIELD: FieldDraft = { label: '', fieldType: 'integer', required: true }

function fromTemplate(t: LogTemplateOut): Draft {
  return {
    id: t.id, name: t.name, shift: t.shift ?? '', active: t.active,
    fields: t.fields.map((f) => ({ id: f.id, label: f.label, fieldType: f.fieldType, required: f.required })),
    departmentIds: t.audience.filter((r) => r.type === 'department').map((r) => r.id),
    userIds: t.audience.filter((r) => r.type === 'user').map((r) => r.id),
  }
}

function toggle(list: string[], id: string, on: boolean): string[] {
  return on ? [...list, id] : list.filter((x) => x !== id)
}

/** Specific to this screen rather than a bent ItemListEditor: log fields have their own types and
 *  no bounds or units (spec §4.3). A saved field's type is locked, as the server requires. */
function FieldListEditor({ fields, onChange, error }: {
  fields: FieldDraft[]
  onChange: (fields: FieldDraft[]) => void
  error?: string
}) {
  const edit = (index: number, change: Partial<FieldDraft>) =>
    onChange(fields.map((f, i) => (i === index ? { ...f, ...change } : f)))
  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= fields.length) return
    const next = [...fields]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }

  return (
    <div>
      <div className="mb-1 flex items-center">
        <p className={LABEL}>Fields</p>
        <Button className="ml-auto" onClick={() => onChange([...fields, { ...NEW_FIELD }])}>
          Add field
        </Button>
      </div>
      <FieldError message={error} />
      <ol className="flex flex-col gap-2">
        {fields.map((field, index) => {
          const n = index + 1
          return (
            <li key={field.id ?? `new-${index}`} className="rounded border border-border2 p-2">
              <div className="flex flex-col gap-2">
                <Input aria-label={`Label for field ${n}`} value={field.label} maxLength={200}
                       placeholder="Label" onChange={(e) => edit(index, { label: e.target.value })} />
                <div className="flex gap-2">
                  <select aria-label={`Type for field ${n}`} className={SELECT} value={field.fieldType}
                          disabled={Boolean(field.id)}
                          onChange={(e) => edit(index, { fieldType: e.target.value as LogFieldType })}>
                    {(Object.keys(FIELD_TYPE_LABELS) as LogFieldType[]).map((t) => (
                      <option key={t} value={t}>{FIELD_TYPE_LABELS[t]}</option>
                    ))}
                  </select>
                  <label className="flex items-center gap-1 text-xs">
                    <input type="checkbox" aria-label={`Field ${n} required`} checked={field.required}
                           onChange={(e) => edit(index, { required: e.target.checked })} />
                    Required
                  </label>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" aria-label={`Move field ${n} up`} onClick={() => move(index, -1)}>↑</Button>
                  <Button variant="ghost" aria-label={`Move field ${n} down`} onClick={() => move(index, 1)}>↓</Button>
                  <Button variant="ghost" className="ml-auto text-dangerText" aria-label={`Remove field ${n}`}
                          onClick={() => onChange(fields.filter((_, i) => i !== index))}>
                    Remove
                  </Button>
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function LogTemplatesAdmin() {
  const { data, isPending, error } = useAdminLogTemplates()
  const { data: departments } = useDepartments()
  const { data: staff } = useStaff()
  const create = useCreateLogTemplate()
  const patch = usePatchLogTemplate()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<LogTemplateOut | null>(null)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)
  const people = (staff ?? []).filter((u) => u.status === 'active')

  const columns: Column<LogTemplateOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'shift', head: 'Shift', render: (r) => (r.shift ? SHIFT_LABELS[r.shift] : 'Any') },
    { key: 'fields', head: 'Fields', mono: true, render: (r) => r.fields.length },
    { key: 'audience', head: 'Shared with', render: (r) => audienceSummary(r.audience) },
    { key: 'used', head: 'Used', mono: true, render: (r) => r.usedCount },
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

  function open(template: LogTemplateOut) {
    clearFailures()
    setSelected(template)
    setDraft(fromTemplate(template))
  }

  function save() {
    if (!draft || !draft.name.trim()) return
    const body: LogTemplateIn = {
      name: draft.name.trim(),
      shift: draft.shift || null,
      active: draft.active,
      // `fields` is a non-empty tuple in the generated type; the server enforces "at least one
      // field" itself (a 400 on save), so the cast mirrors that contract.
      fields: draft.fields.map((f) => ({
        ...(f.id ? { id: f.id } : {}), label: f.label.trim(), fieldType: f.fieldType, required: f.required,
      })) as LogTemplateIn['fields'],
      audience: [
        ...draft.departmentIds.map((id) => ({ type: 'department' as const, id })),
        ...draft.userIds.map((id) => ({ type: 'user' as const, id })),
      ],
    }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Log templates</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              clearFailures()
              setSelected(null)
              setDraft({ ...EMPTY, fields: [], departmentIds: [], userIds: [] })
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
            <EmptyState title="No log templates" hint="A template is a structured shift report staff fill in instead of free text." />
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
            <label className={LABEL} htmlFor="log-tpl-name">Name</label>
            <Input id="log-tpl-name" value={draft.name} maxLength={200} onChange={(e) => edit({ name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="log-tpl-shift">Shift</label>
            <select id="log-tpl-shift" className={SELECT} value={draft.shift}
                    onChange={(e) => edit({ shift: e.target.value as Shift | '' })}>
              <option value="">Any</option>
              {(Object.keys(SHIFT_LABELS) as Shift[]).map((s) => (
                <option key={s} value={s}>{SHIFT_LABELS[s]}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
            Active
          </label>

          <FieldListEditor fields={draft.fields} onChange={(next) => edit({ fields: next })} error={fields.fields} />

          <fieldset>
            <legend className={LABEL}>Shared with</legend>
            <p className="mb-2 text-xs text-text3">Nobody ticked means everyone at the property.</p>
            <FieldError message={fields.audience} />
            <p className="mb-1 text-xs font-semibold text-text3">Departments</p>
            <div className="mb-2 flex flex-col gap-1">
              {(departments ?? []).map((d) => (
                <label key={d.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={draft.departmentIds.includes(d.id)}
                         onChange={(e) => edit({ departmentIds: toggle(draft.departmentIds, d.id, e.target.checked) })} />
                  {d.name}
                </label>
              ))}
            </div>
            <p className="mb-1 text-xs font-semibold text-text3">People</p>
            <div className="flex max-h-48 flex-col gap-1 overflow-y-auto">
              {people.map((u) => (
                <label key={u.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={draft.userIds.includes(u.id)}
                         onChange={(e) => edit({ userIds: toggle(draft.userIds, u.id, e.target.checked) })} />
                  {u.firstName} {u.lastName}
                </label>
              ))}
            </div>
          </fieldset>
        </EditPanel>
      ) : null}
    </div>
  )
}
