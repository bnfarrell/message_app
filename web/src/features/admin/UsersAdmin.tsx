import { useState } from 'react'
import {
  useCreateStaff, useDeleteStaff, useDepartments, usePatchStaff, useStaff,
} from '../../api/hooks/users'
import type { Role, StaffUserOut } from '../../api/types'
import { Button, EmptyState, Input, Spinner } from '../../components/ui'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'

type Draft = {
  id?: string
  firstName: string
  lastName: string
  email: string
  role: Role
  departmentId: string | null
  password: string | null
  phone: string | null
}

const EMPTY: Draft = {
  firstName: '', lastName: '', email: '', role: 'agent', departmentId: null, password: null, phone: null,
}

const ROLES: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function UsersAdmin() {
  const { data, isPending, error } = useStaff()
  const { data: departments } = useDepartments()
  const create = useCreateStaff()
  const patch = usePatchStaff()
  const remove = useDeleteStaff()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<StaffUserOut | null>(null)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending || remove.isPending
  const failure = (create.error ?? patch.error ?? remove.error)?.message ?? null
  const draftId = draft?.id

  const columns: Column<StaffUserOut>[] = [
    { key: 'name', head: 'Name', render: (r) => `${r.firstName} ${r.lastName}` },
    { key: 'email', head: 'Email', render: (r) => r.email },
    { key: 'role', head: 'Role', render: (r) => r.role },
    {
      key: 'dept',
      head: 'Department',
      render: (r) => departments?.find((d) => d.id === r.departmentId)?.name ?? '—',
    },
  ]

  function open(user: StaffUserOut) {
    setSelected(user)
    setDraft({
      id: user.id,
      firstName: user.firstName,
      lastName: user.lastName,
      email: user.email,
      role: user.role,
      departmentId: user.departmentId ?? null,
      password: null,
      phone: null,
    })
  }

  function save() {
    if (!draft) return
    const done = () => {
      setDraft(null)
      setSelected(null)
    }
    if (draft.id) {
      patch.mutate(
        { id: draft.id, role: draft.role, departmentId: draft.departmentId },
        { onSuccess: done },
      )
      return
    }
    if (!draft.firstName.trim() || !draft.lastName.trim() || !draft.email.trim()) return
    create.mutate(
      {
        firstName: draft.firstName,
        lastName: draft.lastName,
        email: draft.email,
        role: draft.role,
        departmentId: draft.departmentId,
        password: draft.password,
        phone: draft.phone,
      },
      { onSuccess: done },
    )
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Users &amp; roles</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              setSelected(null)
              setDraft({ ...EMPTY })
            }}
          >
            New user
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load staff" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No staff" hint="Add one to get started." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          subjectId={draftId ?? 'new'}
          title={draft.id ? 'Edit user' : 'New user'}
          saving={pending}
          error={failure}
          onSave={save}
          onCancel={() => {
            setDraft(null)
            setSelected(null)
          }}
          onDelete={
            draftId
              ? () =>
                  remove.mutate({ id: draftId }, {
                    onSuccess: () => {
                      setDraft(null)
                      setSelected(null)
                    },
                  })
              : undefined
          }
        >
          {!draft.id ? (
            <>
              <div>
                <label className={LABEL} htmlFor="user-first">First name</label>
                <Input id="user-first" value={draft.firstName}
                       onChange={(e) => setDraft({ ...draft, firstName: e.target.value })} />
              </div>
              <div>
                <label className={LABEL} htmlFor="user-last">Last name</label>
                <Input id="user-last" value={draft.lastName}
                       onChange={(e) => setDraft({ ...draft, lastName: e.target.value })} />
              </div>
              <div>
                <label className={LABEL} htmlFor="user-email">Email</label>
                <Input id="user-email" type="email" value={draft.email}
                       onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
              </div>
            </>
          ) : null}
          <div>
            <label className={LABEL} htmlFor="user-role">Role</label>
            <select id="user-role" className={SELECT} value={draft.role}
                    onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}>
              {ROLES.map((role) => (
                <option key={role} value={role}>{role}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL} htmlFor="user-dept">Department</label>
            <select id="user-dept" className={SELECT} value={draft.departmentId ?? ''}
                    onChange={(e) => setDraft({ ...draft, departmentId: e.target.value || null })}>
              <option value="">None</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
          {!draft.id ? (
            <>
              <div>
                <label className={LABEL} htmlFor="user-password">Password</label>
                <Input id="user-password" type="password" value={draft.password ?? ''}
                       onChange={(e) => setDraft({ ...draft, password: e.target.value || null })} />
              </div>
              <div>
                <label className={LABEL} htmlFor="user-phone">Phone</label>
                <Input id="user-phone" value={draft.phone ?? ''}
                       onChange={(e) => setDraft({ ...draft, phone: e.target.value || null })} />
              </div>
            </>
          ) : null}
        </EditPanel>
      ) : null}
    </div>
  )
}
