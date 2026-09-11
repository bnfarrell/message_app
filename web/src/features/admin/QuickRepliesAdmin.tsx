import { useState } from 'react'
import {
  useCreateQuickReply, useDeleteQuickReply, usePatchQuickReply, useQuickReplies,
} from '../../api/hooks/content'
import { useDepartments } from '../../api/hooks/users'
import type { QuickReplyOut } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner, Textarea } from '../../components/ui'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'

type Draft = {
  id?: string
  shortcut: string
  title: string
  body: string
  departmentId: string | null
  category: string | null
  locale: string
  active: boolean
}

const EMPTY: Draft = {
  shortcut: '', title: '', body: '', departmentId: null, category: null, locale: 'en', active: true,
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function QuickRepliesAdmin() {
  const [search, setSearch] = useState('')
  const { data, isPending, error } = useQuickReplies(search || undefined)
  const { data: departments } = useDepartments()
  const create = useCreateQuickReply()
  const patch = usePatchQuickReply()
  const remove = useDeleteQuickReply()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<QuickReplyOut | null>(null)

  const rows = data ?? []
  const activeCount = rows.filter((r) => r.active).length
  const pending = create.isPending || patch.isPending || remove.isPending
  const failure = (create.error ?? patch.error ?? remove.error)?.message ?? null
  const draftId = draft?.id

  const columns: Column<QuickReplyOut>[] = [
    { key: 'shortcut', head: 'Shortcut', mono: true, render: (r) => r.shortcut },
    { key: 'title', head: 'Title', render: (r) => r.title },
    {
      key: 'body',
      head: 'Body',
      render: (r) => <span className="text-text3">{r.body.slice(0, 70)}…</span>,
    },
    {
      key: 'dept',
      head: 'Dept',
      render: (r) => departments?.find((d) => d.id === r.departmentId)?.name ?? 'All',
    },
    { key: 'uses', head: 'Uses', mono: true, render: (r) => r.usageCount },
    {
      key: 'active',
      head: 'Active',
      render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>),
    },
  ]

  function open(reply: QuickReplyOut) {
    setSelected(reply)
    setDraft({
      id: reply.id,
      shortcut: reply.shortcut,
      title: reply.title,
      body: reply.body,
      departmentId: reply.departmentId ?? null,
      category: reply.category ?? null,
      locale: reply.locale,
      active: reply.active,
    })
  }

  function save() {
    if (!draft || !draft.shortcut.trim() || !draft.title.trim() || !draft.body.trim()) return
    const done = () => {
      setDraft(null)
      setSelected(null)
    }
    if (draft.id) {
      // The server's QuickReplyPatch has no `locale` field (extra="forbid" rejects it), unlike
      // QuickReplyIn on create — send only what patch actually accepts.
      const { id, shortcut, title, body, departmentId, category, active } = draft
      patch.mutate({ id, shortcut, title, body, departmentId, category, active }, { onSuccess: done })
    } else {
      create.mutate(draft, { onSuccess: done })
    }
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <div>
            <h1 className="text-base font-bold">Quick replies</h1>
            <p className="text-xs text-text3">
              {activeCount} active · {rows.length - activeCount} inactive
            </p>
          </div>
          <Input
            className="ml-4 max-w-xs"
            placeholder="Search shortcut or text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              setSelected(null)
              setDraft({ ...EMPTY })
            }}
          >
            New quick reply
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load quick replies" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No quick replies" hint="Create one to get started." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          title={draft.id ? 'Edit quick reply' : 'New quick reply'}
          subtitle={selected ? `${selected.usageCount} uses` : undefined}
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
            <label className={LABEL} htmlFor="qr-shortcut">Shortcut</label>
            <Input id="qr-shortcut" value={draft.shortcut}
                   onChange={(e) => setDraft({ ...draft, shortcut: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-title">Title</label>
            <Input id="qr-title" value={draft.title}
                   onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-body">Body</label>
            <Textarea id="qr-body" rows={6} value={draft.body}
                      onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
            <p className="mt-1 text-xs text-text3">
              {'{{guest_first_name}}'} and {'{{room_number}}'} are filled in when sent.
            </p>
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-dept">Department</label>
            <select id="qr-dept" className={SELECT} value={draft.departmentId ?? ''}
                    onChange={(e) => setDraft({ ...draft, departmentId: e.target.value || null })}>
              <option value="">All</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
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
