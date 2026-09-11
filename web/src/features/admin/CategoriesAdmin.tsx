import { useState } from 'react'
import { useCategories, useCreateCategory, useDeleteCategory, usePatchCategory } from '../../api/hooks/content'
import type { CategoryOut } from '../../api/types'
import { Badge, Button, EmptyState, Spinner, Input } from '../../components/ui'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'

type Draft = { id?: string; name: string; parentId: string | null; active: boolean }

const EMPTY: Draft = { name: '', parentId: null, active: true }

type FlatCategory = CategoryOut & { depth: number; parentName: string | null }

function flatten(categories: CategoryOut[], depth = 0, parentName: string | null = null): FlatCategory[] {
  return categories.flatMap((c) => [
    { ...c, depth, parentName },
    ...flatten(c.children ?? [], depth + 1, c.name),
  ])
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function CategoriesAdmin() {
  const { data, isPending, error } = useCategories()
  const create = useCreateCategory()
  const patch = usePatchCategory()
  const remove = useDeleteCategory()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<FlatCategory | null>(null)

  const rows = flatten(data ?? [])
  const pending = create.isPending || patch.isPending || remove.isPending
  const failure = (create.error ?? patch.error ?? remove.error)?.message ?? null
  const draftId = draft?.id

  const columns: Column<FlatCategory>[] = [
    {
      key: 'name',
      head: 'Name',
      render: (r) => <span style={{ paddingLeft: r.depth * 16 }}>{r.name}</span>,
    },
    { key: 'parent', head: 'Parent', render: (r) => r.parentName ?? '—' },
    {
      key: 'active',
      head: 'Active',
      render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>),
    },
  ]

  function open(category: FlatCategory) {
    setSelected(category)
    setDraft({ id: category.id, name: category.name, parentId: category.parentId ?? null, active: category.active })
  }

  function save() {
    if (!draft || !draft.name.trim()) return
    const done = () => {
      setDraft(null)
      setSelected(null)
    }
    if (draft.id) patch.mutate(draft, { onSuccess: done })
    else create.mutate(draft, { onSuccess: done })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Resolution categories</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              setSelected(null)
              setDraft({ ...EMPTY })
            }}
          >
            New category
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load categories" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No categories" hint="Create one to get started." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          title={draft.id ? 'Edit category' : 'New category'}
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
          <div>
            <label className={LABEL} htmlFor="cat-name">Name</label>
            <Input id="cat-name" value={draft.name}
                   onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="cat-parent">Parent</label>
            <select id="cat-parent" className={SELECT} value={draft.parentId ?? ''}
                    onChange={(e) => setDraft({ ...draft, parentId: e.target.value || null })}>
              <option value="">None (top-level)</option>
              {rows.filter((r) => r.id !== draft.id).map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active}
                   onChange={(e) => setDraft({ ...draft, active: e.target.checked })} />
            Active
          </label>
        </EditPanel>
      ) : null}
    </div>
  )
}
