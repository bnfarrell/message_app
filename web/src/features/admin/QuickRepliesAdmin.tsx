import { useEffect, useRef, useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import {
  useCreateQuickReply, useDeleteQuickReply, usePatchQuickReply, useQuickReplies,
  useQuickReplyPreview, useQuickReplyVariables,
} from '../../api/hooks/content'
import { useDepartments } from '../../api/hooks/users'
import type { QuickReplyOut } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner, Textarea } from '../../components/ui'
import { cn } from '../../lib/cn'
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

/** Keeps the preview to one request per pause, not one per keystroke. */
function useDebounced(value: string, ms: number): string {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return settled
}

export function QuickRepliesAdmin() {
  const [search, setSearch] = useState('')
  const { data, isPending, error } = useQuickReplies(search || undefined)
  const { data: departments } = useDepartments()
  const { data: variables, isError: variablesFailed } = useQuickReplyVariables()
  const create = useCreateQuickReply()
  const patch = usePatchQuickReply()
  const remove = useDeleteQuickReply()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<QuickReplyOut | null>(null)
  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const pendingCaret = useRef<number | null>(null)

  const body = draft?.body ?? ''
  const debouncedBody = useDebounced(body, 300)
  const preview = useQuickReplyPreview(debouncedBody)
  // The rendered text belongs to `debouncedBody`; until that catches up and the request settles,
  // what is on screen describes an older draft — possibly a different record's, when the admin
  // clicks from one row to the next — so the pane shows the draft as typed instead, labelled.
  const previewStale = debouncedBody !== body || preview.isFetching
  const previewBody = previewStale ? body : preview.data?.body ?? body

  const rows = data ?? []
  const activeCount = rows.filter((r) => r.active).length
  const pending = create.isPending || patch.isPending || remove.isPending
  const failed = create.error ?? patch.error ?? remove.error
  const failure = failed?.message ?? null
  const fields = fieldErrors(failed)
  const draftId = draft?.id

  // A chip insert changes the controlled value, so the caret can only be placed once React has
  // committed it — otherwise the browser drops it at the end of the new text.
  useEffect(() => {
    const caret = pendingCaret.current
    if (caret === null) return
    pendingCaret.current = null
    bodyRef.current?.focus()
    bodyRef.current?.setSelectionRange(caret, caret)
  }, [body])

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

  /**
   * A mutation error outlives its panel: react-query keeps it until the next mutate. Left alone,
   * opening a different row shows the previous record's banner and — worse, since the message is
   * pinned to a specific box — a red field error under an input holding a perfectly valid value.
   */
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

  function open(reply: QuickReplyOut) {
    clearFailures()
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

  function insertVariable(name: string) {
    if (!draft) return
    const token = `{{${name}}}`
    const el = bodyRef.current
    const start = el?.selectionStart ?? draft.body.length
    const end = el?.selectionEnd ?? draft.body.length
    pendingCaret.current = start + token.length
    setDraft({ ...draft, body: draft.body.slice(0, start) + token + draft.body.slice(end) })
  }

  function save() {
    if (!draft || !draft.shortcut.trim() || !draft.title.trim() || !draft.body.trim()) return
    // Every field on the draft is patchable: A1 added `locale` to QuickReplyPatch, so the old
    // "strip locale, extra=forbid rejects it" carve-out is gone.
    if (draft.id) patch.mutate(draft, { onSuccess: close })
    else create.mutate(draft, { onSuccess: close })
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
              clearFailures()
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
          subjectId={draftId ?? 'new'}
          title={draft.id ? 'Edit quick reply' : 'New quick reply'}
          subtitle={selected ? `${selected.usageCount} uses` : undefined}
          saving={pending}
          error={failure}
          onSave={save}
          onCancel={close}
          onDelete={draftId ? () => remove.mutate({ id: draftId }, { onSuccess: close }) : undefined}
        >
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL} htmlFor="qr-shortcut">Shortcut</label>
              <Input id="qr-shortcut" className="font-mono" value={draft.shortcut}
                     onChange={(e) => setDraft({ ...draft, shortcut: e.target.value })} />
              <FieldError message={fields.shortcut} />
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
              <FieldError message={fields.departmentId} />
            </div>
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-title">Title</label>
            <Input id="qr-title" value={draft.title}
                   onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            <FieldError message={fields.title} />
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-body">Body</label>
            {/* QuickReplyIn.body and PreviewRequest.body are both capped at 1600; without this
                the preview answers the generic "Invalid request body" and never says why. */}
            <Textarea id="qr-body" ref={bodyRef} rows={6} value={draft.body} maxLength={1600}
                      onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
            <FieldError message={fields.body} />
            {variables?.length ? (
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-text3">
                Insert:
                {variables.map((name) => (
                  <button
                    key={name}
                    type="button"
                    // Keeps the textarea's selection alive across the click, so the token lands
                    // where the caret already was rather than at the end of the body.
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => insertVariable(name)}
                    className="rounded-md bg-tagBg px-2 py-1 font-mono text-xs text-roomNum hover:bg-sel"
                  >
                    {name}
                  </button>
                ))}
              </div>
            ) : variablesFailed ? (
              // The chips replaced a static hint that named the variables. If the list cannot be
              // fetched, say they exist rather than leaving a bare "Insert:" or nothing at all —
              // without naming them here, which would be the hardcoded copy the chips avoid.
              <p className="mt-1.5 text-xs text-text3">
                {'{{variable_name}}'} placeholders are filled in when the reply is sent. The list of
                names could not be loaded.
              </p>
            ) : null}
          </div>

          {draft.body ? (
            <div>
              {/* Not "Preview as <guest>": this renders the server's sample values, so naming a
                  real guest would be a lie. See the A2 report's disclosed divergences. */}
              <span className={LABEL}>Preview · sample values</span>
              {preview.error ? (
                <p className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
                  Preview unavailable: {preview.error.message}
                </p>
              ) : (
                <>
                  <div
                    aria-busy={previewStale}
                    className={cn(
                      'rounded px-3 py-2 text-sm leading-relaxed bg-outBg text-outText',
                      previewStale && 'opacity-60',
                    )}
                  >
                    {previewBody}
                  </div>
                  <p className="mt-1 font-mono text-xs text-text3">
                    {previewStale || !preview.data
                      ? 'Updating…'
                      // Server-computed: server/app/domain/sms.py is the count that bills.
                      : `${preview.data.characters} chars · ${preview.data.segments} segment${
                          preview.data.segments === 1 ? '' : 's'
                        }`}
                  </p>
                </>
              )}
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL} htmlFor="qr-category">Category</label>
              <Input id="qr-category" value={draft.category ?? ''}
                     placeholder="Optional"
                     onChange={(e) => setDraft({ ...draft, category: e.target.value || null })} />
              <FieldError message={fields.category} />
            </div>
            <div>
              <label className={LABEL} htmlFor="qr-locale">Locale</label>
              <Input id="qr-locale" value={draft.locale} maxLength={8}
                     onChange={(e) => setDraft({ ...draft, locale: e.target.value })} />
              <FieldError message={fields.locale} />
            </div>
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

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}
