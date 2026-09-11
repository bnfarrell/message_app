import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import {
  useCreateDepartment, useDeleteDepartment, useDepartments, usePatchDepartment,
} from '../../api/hooks/users'
import type { DepartmentOut, DepartmentType } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'

// Full CRUD since wave A1 added POST / PATCH / DELETE /api/p/<id>/departments. The header that
// used to stand here said the screen was read-only "by design"; that constraint is gone.
//
// Disclosed divergence: Admin.dc.html draws no create affordance for Departments, so the New
// button and the edit panel are not in the mockup. They are here on the user's decision to make
// this screen editable, which is the same authority the mockup itself carries.
//
// `escalationMinutes` is a column here and deliberately NOT a field in the panel (ruling D81):
// nothing in the codebase computes with it — the SLA that is actually enforced is the
// property-level `slaMinutes` on Property settings — so an editable control would change a number
// no reader reads. Showing the stored value plainly is the honest half of that.

type Draft = { id?: string; name: string; type: DepartmentType; active: boolean }

// Keyed by the union rather than listed as an array so TypeScript refuses to compile when the
// server grows a ninth DepartmentType: an array typed `DepartmentType[]` catches a wrong value
// but never a missing one, and a missing one here is a type the admin simply cannot pick.
const TYPE_LABELS: Record<DepartmentType, string> = {
  front_desk: 'Front desk',
  housekeeping: 'Housekeeping',
  engineering: 'Engineering',
  food_beverage: 'Food & beverage',
  spa: 'Spa',
  security: 'Security',
  valet: 'Valet',
  other: 'Other',
}

// `other`, not `front_desk`: the type is load-bearing, not decorative. notifications.py routes
// unassigned-conversation alerts to the department whose type is `front_desk`, and
// work_orders.py filters by type too, so a default that silently claimed one of those roles
// would be worse than one that claims none.
const EMPTY: Draft = { name: '', type: 'other', active: true }

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function DepartmentsAdmin() {
  const { data, isPending, error } = useDepartments()
  const create = useCreateDepartment()
  const patch = usePatchDepartment()
  const remove = useDeleteDepartment()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<DepartmentOut | null>(null)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending || remove.isPending
  const failed = create.error ?? patch.error ?? remove.error
  // The delete guard's 409 message is written to be read by an admin — it names what still
  // references the department and points at deactivating instead — so it is surfaced verbatim
  // rather than replaced with a generic failure.
  const failure = failed?.message ?? null
  const fields = fieldErrors(failed)
  const draftId = draft?.id

  const columns: Column<DepartmentOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'type', head: 'Type', render: (r) => TYPE_LABELS[r.type] },
    {
      key: 'escalation',
      head: 'Escalation',
      mono: true,
      render: (r) => `${r.escalationMinutes} min`,
    },
    {
      key: 'active',
      head: 'Active',
      render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>),
    },
  ]

  /** A mutation error outlives its panel; without this, opening another row shows its banner. */
  function clearFailures() {
    create.reset()
    patch.reset()
    remove.reset()
  }

  function close() {
    clearFailures()
    setDraft(null)
    setSelected(null)
  }

  function open(department: DepartmentOut) {
    clearFailures()
    setSelected(department)
    setDraft({
      id: department.id,
      name: department.name,
      type: department.type,
      active: department.active,
    })
  }

  function save() {
    if (!draft || !draft.name.trim()) return
    const body = { name: draft.name, type: draft.type, active: draft.active }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    // escalationMinutes is omitted on create: DepartmentIn defaults it to 15, and the panel has
    // no control for it (D81), so sending a value the form never collected would be invention.
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Departments</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              clearFailures()
              setSelected(null)
              setDraft({ ...EMPTY })
            }}
          >
            New department
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load departments" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No departments" hint="Create one to get started." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable
                columns={columns}
                rows={rows}
                selectedId={selected?.id ?? null}
                onSelect={open}
              />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          // Remount per subject. EditPanel holds its delete confirmation in local state, and the
          // panel does not unmount when the admin clicks from one row to the next — so a Delete
          // pressed on a department the guard then refuses leaves "Confirm" armed over the NEXT
          // row the admin opens, one click from deleting something they never asked about. The
          // key is scoped to this screen; the same carry-over exists on the other four panels and
          // is recorded rather than fixed here.
          key={draftId ?? 'new'}
          title={draft.id ? 'Edit department' : 'New department'}
          saving={pending}
          error={failure}
          onSave={save}
          onCancel={close}
          onDelete={draftId ? () => remove.mutate({ id: draftId }, { onSuccess: close }) : undefined}
        >
          <div>
            <label className={LABEL} htmlFor="dept-name">Name</label>
            <Input id="dept-name" value={draft.name} maxLength={100}
                   onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="dept-type">Type</label>
            <select id="dept-type" className={SELECT} value={draft.type}
                    onChange={(e) => setDraft({ ...draft, type: e.target.value as DepartmentType })}>
              {(Object.keys(TYPE_LABELS) as DepartmentType[]).map((type) => (
                <option key={type} value={type}>{TYPE_LABELS[type]}</option>
              ))}
            </select>
            <FieldError message={fields.type} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active}
                   onChange={(e) => setDraft({ ...draft, active: e.target.checked })} />
            Active
          </label>
          {/* The escape hatch the delete guard's message points at: a department that is still
              referenced cannot be deleted, but it can be switched off so nothing picks it. */}
          <p className="text-xs text-text3">
            A department that is still in use cannot be deleted. Clear Active instead — it then
            stops appearing in the pickers without disturbing what already references it.
          </p>
        </EditPanel>
      ) : null}
    </div>
  )
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}
