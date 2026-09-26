import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreateChecklistTemplate, usePatchChecklistTemplate, useChecklistTemplates } from '../../api/hooks/checklists'
import { useDepartments } from '../../api/hooks/users'
import type { ChecklistKind, ChecklistSchedule, ChecklistTemplateIn, ChecklistTemplateOut, Shift } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { KIND_LABELS, SHIFT_LABELS, WEEKDAYS, scheduleLabel } from '../checklists/labels'
import { AdminTable, type Column } from './AdminTable'
import { CategoryListEditor, type CategoryDraft } from './CategoryListEditor'
import { EditPanel } from './EditPanel'
import { FieldError, ItemListEditor, itemDraftFrom, orderByCategory, toItemIn, type ItemDraft } from './ItemListEditor'
import { LibraryImportDialog } from './LibraryImportDialog'

type Draft = {
  id?: string
  name: string
  departmentId: string
  schedule: ChecklistSchedule
  shift: Shift
  days: boolean[]
  active: boolean
  kind: ChecklistKind
  categories: CategoryDraft[]
  items: ItemDraft[]
}

const EMPTY: Draft = {
  name: '', departmentId: '', schedule: 'weekly', shift: 'am',
  days: [true, true, true, true, true, true, true], active: true, kind: 'normal', categories: [], items: [],
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

const SCHEDULES: [ChecklistSchedule, string][] = [
  ['weekly', 'Weekly'], ['on_demand', 'On demand'], ['unscheduled', 'Not scheduled yet'],
]
const KINDS: ChecklistKind[] = ['normal', 'readings']

function fromTemplate(t: ChecklistTemplateOut): Draft {
  const mask = t.weekdays ?? 0
  return {
    id: t.id, name: t.name, departmentId: t.departmentId ?? '', schedule: t.schedule,
    shift: t.shift ?? 'am',
    days: WEEKDAYS.map((_, i) => Boolean((mask >> i) & 1)),
    active: t.active,
    kind: t.kind,
    // A saved category's key is its id, so the items' categoryId can point straight at it.
    categories: t.categories.map((c) => ({ key: c.id, id: c.id, name: c.name })),
    items: (t.items ?? []).map((i) => ({ ...itemDraftFrom(i), categoryKey: i.categoryId ?? null })),
  }
}

export function ChecklistTemplatesAdmin() {
  const { data, isPending, error } = useChecklistTemplates()
  const { data: departments } = useDepartments()
  const create = useCreateChecklistTemplate()
  const patch = usePatchChecklistTemplate()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<ChecklistTemplateOut | null>(null)
  const [kindFilter, setKindFilter] = useState<ChecklistKind | null>(null)
  const [importing, setImporting] = useState(false)

  const all = data ?? []
  const rows = kindFilter ? all.filter((r) => r.kind === kindFilter) : all
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)
  const noDaysTicked = draft?.schedule === 'weekly' && !draft.days.some(Boolean)
  const unnamedCategory = Boolean(draft?.categories.some((c) => !c.name.trim()))

  const columns: Column<ChecklistTemplateOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    {
      key: 'kind', head: 'Kind',
      render: (r) => <Badge tone={r.kind === 'readings' ? 'note' : 'neutral'}>{KIND_LABELS[r.kind]}</Badge>,
    },
    { key: 'department', head: 'Department', render: (r) => r.departmentName ?? '' },
    {
      key: 'schedule', head: 'Schedule',
      render: (r) => r.schedule === 'unscheduled'
        ? <span className="font-semibold text-accent">{scheduleLabel(r)}</span>
        : scheduleLabel(r),
    },
    { key: 'categories', head: 'Categories', mono: true, render: (r) => r.categories.length },
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

  /** Removing a category leaves its items ungrouped (checklist structure spec §2.2). */
  function editCategories(categories: CategoryDraft[]) {
    if (!draft) return
    const keys = new Set(categories.map((c) => c.key))
    setDraft({
      ...draft, categories,
      items: draft.items.map((i) => (i.categoryKey && !keys.has(i.categoryKey) ? { ...i, categoryKey: null } : i)),
    })
  }

  function open(template: ChecklistTemplateOut) {
    clearFailures()
    setSelected(template)
    setDraft(fromTemplate(template))
  }

  function save() {
    if (!draft || !draft.name.trim() || noDaysTicked || unnamedCategory) return
    const weekly = draft.schedule === 'weekly'
    const keys = new Set(draft.categories.map((c) => c.key))
    const body: ChecklistTemplateIn = {
      name: draft.name.trim(), departmentId: draft.departmentId, schedule: draft.schedule,
      shift: weekly ? draft.shift : null,
      weekdays: weekly
        ? draft.days.reduce((mask, on, i) => (on ? mask | (1 << i) : mask), 0) : null,
      active: draft.active, kind: draft.kind,
      categories: draft.categories.map((c) => ({ key: c.key, ...(c.id ? { id: c.id } : {}), name: c.name.trim() })),
      // Items1 is a non-empty tuple; the server itself enforces "at least one item"
      // (ValidationFailed on save), so a cast here is safe and mirrors that contract.
      // Saved in the grouped order the editor shows, so positions match what the admin saw.
      items: orderByCategory(draft.items, draft.categories).map((i) => ({
        ...toItemIn(i),
        categoryKey: i.categoryKey && keys.has(i.categoryKey) ? i.categoryKey : null,
      })) as ChecklistTemplateIn['items'],
    }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Checklist templates</h1>
          <div className="flex gap-1.5">
            {KINDS.map((kind) => (
              <button
                key={kind}
                type="button"
                aria-pressed={kindFilter === kind}
                onClick={() => setKindFilter(kindFilter === kind ? null : kind)}
                className={cn(
                  'inline-flex h-8 items-center rounded px-3 text-xs font-semibold',
                  kindFilter === kind ? 'bg-accent text-accentText' : 'bg-surface2 text-text3 hover:text-text',
                )}
              >
                {KIND_LABELS[kind]} {all.filter((r) => r.kind === kind).length}
              </button>
            ))}
          </div>
          <Button className="ml-auto" onClick={() => setImporting(true)}>
            Import from library
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              clearFailures()
              setSelected(null)
              setDraft({ ...EMPTY, categories: [], items: [] })
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

      <LibraryImportDialog
        open={importing}
        onClose={() => setImporting(false)}
        onImported={(template) => {
          setImporting(false)
          open(template)
        }}
      />

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

          <div>
            <p className={LABEL}>Kind</p>
            <div className="flex gap-4">
              {KINDS.map((kind) => (
                <label key={kind} className="flex items-center gap-2 text-sm">
                  <input type="radio" name="kind" checked={draft.kind === kind}
                         onChange={() => edit({ kind })} />
                  {KIND_LABELS[kind]}
                </label>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-4">
            {SCHEDULES.map(([schedule, label]) => (
              <label key={schedule} className="flex items-center gap-2 text-sm">
                <input type="radio" name="schedule" checked={draft.schedule === schedule}
                       onChange={() => edit({ schedule })} />
                {label}
              </label>
            ))}
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
                <FieldError message={fields.weekdays ?? (noDaysTicked ? 'Pick at least one day' : undefined)} />
              </div>
            </>
          ) : draft.schedule === 'unscheduled' ? (
            <p className="text-xs text-text3">
              Saved without a schedule, it never appears on the Checklists page. Pick Weekly or On
              demand when it is ready.
            </p>
          ) : null}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
            Active
          </label>

          <CategoryListEditor
            categories={draft.categories}
            onChange={editCategories}
            error={fields.categories ?? (unnamedCategory ? 'Name every category' : undefined)}
          />

          <ItemListEditor items={draft.items} onChange={(items) => edit({ items })} error={fields.items}
                          categories={draft.categories} />
        </EditPanel>
      ) : null}
    </div>
  )
}
