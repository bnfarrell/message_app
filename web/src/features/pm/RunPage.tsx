import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  useBeginRun, useCompleteRun, useInspectRun, usePmRun, useSaveAnswer, useUploadRunPhoto,
} from '../../api/hooks/pm'
import { useSession } from '../../auth/SessionContext'
import { Badge, Button, EmptyState, Spinner, Textarea, useToast } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { ChecklistItem } from './ChecklistItem'
import { RUN_STATUS_LABELS } from './labels'

const STATUS_TONE = {
  pending: 'neutral', in_progress: 'note', completed: 'warn', passed: 'ok', failed: 'danger',
  missed: 'danger',
} as const

export function RunPage() {
  const { id } = useParams<{ id: string }>()
  const { can } = useSession()
  const toast = useToast()
  const { data: run, isPending, error } = usePmRun(id)
  const save = useSaveAnswer()
  const upload = useUploadRunPhoto()
  const complete = useCompleteRun()
  const begin = useBeginRun()
  const inspect = useInspectRun()
  const [failing, setFailing] = useState(false)
  const [note, setNote] = useState('')

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !run) return <EmptyState title="Could not load this PM" hint={error?.message} />

  const fail = (err: { message: string }) => toast(err.message, 'danger')
  const readOnly = run.status !== 'in_progress' || !can('perform_pm')
  const canInspect = run.status === 'completed' && can('inspect_pm')
  const items = run.items ?? []
  const answers = run.answers ?? []
  const photos = run.photos ?? []
  const missing = new Set(run.missingRequired ?? [])
  const missingLabels = items.filter((i) => missing.has(i.id)).map((i) => i.label)
  const answerFor = (itemId: string) => answers.find((a) => a.itemId === itemId)
  const general = photos.filter((p) => !p.itemId)

  const back = run.workOrderId ? (
    <Link to={`/app/work-orders/${run.workOrderId}`} className="text-sm font-semibold text-text3 hover:text-text">
      ← Work order
    </Link>
  ) : (
    <Link to={`/app/pm?kind=${run.unitKind}`} className="text-sm font-semibold text-text3 hover:text-text">
      ← Sweep
    </Link>
  )

  return (
    <div className="h-full overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        {back}
        <span className="font-mono text-lg font-bold text-roomNum">{run.unitCode}</span>
        <h1 className="text-base font-bold">{run.unitName}</h1>
        <Badge tone={STATUS_TONE[run.status]}>{RUN_STATUS_LABELS[run.status]}</Badge>
        <span className="w-full text-xs text-text3 md:ml-auto md:w-auto">
          {run.templateName}
          {run.startedByName ? ` · ${run.startedByName}` : ''}
          {run.startedAt ? ` · started ${formatClock(run.startedAt)}` : ''}
          {run.dueAt ? ` · due ${new Date(run.dueAt).toLocaleDateString()}` : ''}
        </span>
      </header>

      <div className="mx-auto flex max-w-2xl flex-col gap-3 p-4">
        {run.status === 'pending' ? (
          can('perform_pm') ? (
            <EmptyState
              title="This PM is scheduled and waiting to be picked up"
              action={
                <Button variant="primary" loading={begin.isPending}
                        onClick={() => begin.mutate(run.id, { onError: fail })}>
                  Start PM
                </Button>
              }
            />
          ) : (
            <EmptyState title="This PM is scheduled and waiting to be picked up" />
          )
        ) : (
          <ol className="flex flex-col gap-3">
            {items.map((item) => (
              <ChecklistItem
                key={item.id}
                item={item}
                answer={answerFor(item.id)}
                photos={photos.filter((p) => p.itemId === item.id)}
                readOnly={readOnly}
                missing={missing.has(item.id)}
                onSave={(patch) => {
                  const answer = answerFor(item.id)
                  if (answer) save.mutate({ runId: run.id, answerId: answer.id, patch }, { onError: fail })
                }}
                onUpload={(file) => upload.mutate({ runId: run.id, file, itemId: item.id }, { onError: fail })}
              />
            ))}
          </ol>
        )}

        {run.status !== 'pending' ? (
          <section className="rounded-card border border-border2 bg-surface p-4">
            <h2 className="text-xs font-bold uppercase tracking-widest text-text3">Other photos</h2>
            {general.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {general.map((photo) => (
                  <a key={photo.id} href={photo.url} target="_blank" rel="noreferrer">
                    <img src={photo.url} alt="" className="h-20 w-20 rounded object-cover" />
                  </a>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-xs text-text3">None</p>
            )}
            {readOnly ? null : (
              <input
                type="file"
                aria-label="Add a photo"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                className="mt-2 block text-sm"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) upload.mutate({ runId: run.id, file }, { onError: fail })
                  event.target.value = ''
                }}
              />
            )}
          </section>
        ) : null}

        {!readOnly ? (
          <footer className="flex flex-wrap items-center gap-3 rounded-card border border-border2 bg-surface p-4">
            <Button
              variant="primary"
              disabled={missing.size > 0}
              loading={complete.isPending}
              onClick={() => complete.mutate(run.id, { onError: fail })}
            >
              Complete
            </Button>
            {missing.size > 0 ? (
              <p className="text-xs text-text3">
                {missing.size} required item{missing.size === 1 ? '' : 's'} still need{missing.size === 1 ? 's' : ''} an answer: {missingLabels.join(', ')}
              </p>
            ) : (
              <p className="text-xs text-text3">Everything required is answered.</p>
            )}
          </footer>
        ) : null}

        {canInspect ? (
          <footer className="flex flex-col gap-3 rounded-card border border-border2 bg-surface p-4">
            <p className="text-sm font-semibold">Inspection</p>
            {failing ? (
              <>
                <label className="text-xs font-bold uppercase tracking-widest text-text3" htmlFor="pm-fail-note">
                  What must be redone
                </label>
                <Textarea id="pm-fail-note" value={note} maxLength={2000}
                          onChange={(event) => setNote(event.target.value)} />
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    disabled={!note.trim()}
                    loading={inspect.isPending}
                    onClick={() => inspect.mutate({ runId: run.id, body: { result: 'fail', note: note.trim() } }, { onError: fail })}
                  >
                    Record failure
                  </Button>
                  <Button onClick={() => setFailing(false)}>Back</Button>
                </div>
              </>
            ) : (
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  loading={inspect.isPending}
                  onClick={() => inspect.mutate({ runId: run.id, body: { result: 'pass' } }, { onError: fail })}
                >
                  Pass
                </Button>
                <Button variant="danger" onClick={() => setFailing(true)}>Fail</Button>
              </div>
            )}
          </footer>
        ) : null}

        {run.inspectionNote ? (
          <p className="rounded border border-dangerText/40 bg-dangerBg px-3 py-2 text-sm text-dangerText">
            Inspector{run.inspectedByName ? ` (${run.inspectedByName})` : ''}: {run.inspectionNote}
          </p>
        ) : null}
      </div>
    </div>
  )
}
