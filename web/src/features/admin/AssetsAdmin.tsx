import { useState } from 'react'
import { useAssets, useCreateAsset, useDeleteAsset, usePatchAsset } from '../../api/hooks/content'
import { useDepartments } from '../../api/hooks/users'
import type { AssetOut, AssetType } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner, Textarea } from '../../components/ui'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'

type Draft = {
  id?: string
  name: string
  type: AssetType
  url: string
  description: string | null
  category: string | null
  departmentId: string | null
  validFrom: string | null
  validUntil: string | null
  active: boolean
}

const EMPTY: Draft = {
  name: '', type: 'file', url: '', description: null, category: null, departmentId: null,
  validFrom: null, validUntil: null, active: true,
}

const TYPES: AssetType[] = ['file', 'link', 'menu', 'map', 'form']

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function AssetsAdmin() {
  const { data, isPending, error } = useAssets()
  const { data: departments } = useDepartments()
  const create = useCreateAsset()
  const patch = usePatchAsset()
  const remove = useDeleteAsset()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<AssetOut | null>(null)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending || remove.isPending
  const failure = (create.error ?? patch.error ?? remove.error)?.message ?? null
  const draftId = draft?.id

  const columns: Column<AssetOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'type', head: 'Type', render: (r) => r.type },
    { key: 'shortCode', head: 'Short code', mono: true, render: (r) => r.shortCode },
    { key: 'sends', head: 'Sends', mono: true, render: (r) => r.sendCount },
    {
      key: 'active',
      head: 'Active',
      render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>),
    },
  ]

  function open(asset: AssetOut) {
    setSelected(asset)
    setDraft({
      id: asset.id,
      name: asset.name,
      type: asset.type,
      url: asset.url,
      description: asset.description ?? null,
      category: asset.category ?? null,
      departmentId: asset.departmentId ?? null,
      validFrom: asset.validFrom ?? null,
      validUntil: asset.validUntil ?? null,
      active: asset.active,
    })
  }

  function save() {
    if (!draft || !draft.name.trim() || !draft.url.trim()) return
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
          <h1 className="text-base font-bold">Digital assets</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              setSelected(null)
              setDraft({ ...EMPTY })
            }}
          >
            New asset
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load assets" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No assets" hint="Create one to get started." />
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
          title={draft.id ? 'Edit asset' : 'New asset'}
          subtitle={selected ? `${selected.sendCount} sends` : undefined}
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
            <label className={LABEL} htmlFor="asset-name">Name</label>
            <Input id="asset-name" value={draft.name}
                   onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="asset-type">Type</label>
            <select id="asset-type" className={SELECT} value={draft.type}
                    onChange={(e) => setDraft({ ...draft, type: e.target.value as AssetType })}>
              {TYPES.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL} htmlFor="asset-url">URL</label>
            <Input id="asset-url" value={draft.url}
                   onChange={(e) => setDraft({ ...draft, url: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="asset-description">Description</label>
            <Textarea id="asset-description" rows={3} value={draft.description ?? ''}
                      onChange={(e) => setDraft({ ...draft, description: e.target.value || null })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="asset-category">Category</label>
            <Input id="asset-category" value={draft.category ?? ''}
                   onChange={(e) => setDraft({ ...draft, category: e.target.value || null })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="asset-dept">Department</label>
            <select id="asset-dept" className={SELECT} value={draft.departmentId ?? ''}
                    onChange={(e) => setDraft({ ...draft, departmentId: e.target.value || null })}>
              <option value="">All</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL} htmlFor="asset-valid-from">Valid from</label>
            <Input id="asset-valid-from" placeholder="ISO date-time" value={draft.validFrom ?? ''}
                   onChange={(e) => setDraft({ ...draft, validFrom: e.target.value || null })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="asset-valid-until">Valid until</label>
            <Input id="asset-valid-until" placeholder="ISO date-time" value={draft.validUntil ?? ''}
                   onChange={(e) => setDraft({ ...draft, validUntil: e.target.value || null })} />
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
