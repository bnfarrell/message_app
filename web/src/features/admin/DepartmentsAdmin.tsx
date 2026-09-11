import { useState } from 'react'
import { useDepartments } from '../../api/hooks/users'
import type { DepartmentOut } from '../../api/types'
import { Badge, EmptyState, Spinner } from '../../components/ui'
import { AdminTable, type Column } from './AdminTable'

// Read-only by design: Phase 1 exposes only GET /api/p/<id>/departments (spec §385), so there
// is no create/edit affordance here and no EditPanel — which is also how Admin.dc.html draws it.
export function DepartmentsAdmin() {
  const { data, isPending, error } = useDepartments()
  const [selected, setSelected] = useState<string | null>(null)

  const rows = data ?? []

  const columns: Column<DepartmentOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'type', head: 'Type', render: (r) => r.type.replace(/_/g, ' ') },
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

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Departments</h1>
          <p className="text-xs text-text3">Read-only in Phase 1</p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load departments" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No departments" hint="This property has none configured." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable
                columns={columns}
                rows={rows}
                selectedId={selected}
                onSelect={(row) => setSelected(row.id)}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
