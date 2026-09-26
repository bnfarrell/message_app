import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  useChecklistInstance,
  useCompleteChecklist,
  useSaveChecklistAnswer,
  useSetChecklistComment,
  useStartChecklist,
  useUploadChecklistPhoto,
} from '../../api/hooks/checklists'
import { useSession } from '../../auth/SessionContext'
import { Badge, Button, EmptyState, Spinner, Textarea } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { ChecklistItem } from '../pm/ChecklistItem'
import { SHIFT_LABELS, STATUS_LABELS, STATUS_TONE } from './labels'

export function ChecklistRunPage() {
  const { id } = useParams<{ id: string }>()
  const { can } = useSession()
  const { data: instance, isPending, error } = useChecklistInstance(id)
  const save = useSaveChecklistAnswer()
  const upload = useUploadChecklistPhoto()
  const comment = useSetChecklistComment()
  const complete = useCompleteChecklist()
  const start = useStartChecklist()
  const [note, setNote] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (instance) setNote(instance.comment ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instance?.id, instance?.comment])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !instance) {
    return <EmptyState title="Could not load this checklist" hint={error?.message} />
  }

  const fail = (err: { message: string }) => setActionError(err.message)
  const readOnly = instance.status !== 'in_progress' || !can('perform_checklists')
  const items = instance.items ?? []
  const answers = instance.answers ?? []
  const photos = instance.photos ?? []
  const missing = new Set(instance.missingRequired ?? [])
  const missingLabels = items.filter((i) => missing.has(i.id)).map((i) => i.label)
  const answerFor = (itemId: string) => answers.find((a) => a.itemId === itemId)
  const general = photos.filter((p) => !p.itemId)

  return (
    <div className="h-full overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <Link to="/app/checklists" className="text-sm font-semibold text-text3 hover:text-text">
          ← Checklists
        </Link>
        <h1 className="text-base font-bold">{instance.templateName}</h1>
        <Badge tone={STATUS_TONE[instance.status]}>{STATUS_LABELS[instance.status]}</Badge>
        <span className="w-full text-xs text-text3 md:ml-auto md:w-auto">
          {instance.departmentName} · {SHIFT_LABELS[instance.shift]} · {instance.dueDate}
          {instance.startedByName ? ` · started by ${instance.startedByName}` : ''}
          {instance.startedAt ? ` ${formatClock(instance.startedAt)}` : ''}
          {instance.completedByName ? ` · completed by ${instance.completedByName}` : ''}
          {instance.completedAt ? ` ${formatClock(instance.completedAt)}` : ''}
        </span>
      </header>

      <div className="mx-auto flex max-w-2xl flex-col gap-3 p-4">
        {actionError ? (
          <p role="alert" className="rounded border border-dangerText/40 bg-dangerBg px-3 py-2 text-sm text-dangerText">
            {actionError}
          </p>
        ) : null}

        {instance.status === 'open' ? (
          can('perform_checklists') ? (
            <EmptyState
              title="This checklist is waiting to be started"
              action={
                <Button variant="primary" loading={start.isPending}
                        onClick={() => start.mutate(instance.id, { onError: fail })}>
                  Start
                </Button>
              }
            />
          ) : (
            <EmptyState title="This checklist is waiting to be started" />
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
                  if (answer) {
                    save.mutate({ instanceId: instance.id, answerId: answer.id, patch }, { onError: fail })
                  }
                }}
                onUpload={(file) =>
                  upload.mutate({ instanceId: instance.id, file, itemId: item.id }, { onError: fail })
                }
              />
            ))}
          </ol>
        )}

        {instance.status !== 'open' ? (
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
                  if (file) upload.mutate({ instanceId: instance.id, file }, { onError: fail })
                  event.target.value = ''
                }}
              />
            )}
          </section>
        ) : null}

        <section className="flex flex-col gap-2 rounded-card border border-border2 bg-surface p-4">
          <label className="text-xs font-bold uppercase tracking-widest text-text3" htmlFor="ck-handover-note">
            Handover note
          </label>
          <Textarea
            id="ck-handover-note"
            aria-label="Handover note"
            value={note}
            maxLength={4000}
            disabled={readOnly}
            onChange={(event) => setNote(event.target.value)}
          />
          {readOnly ? null : (
            <div>
              <Button
                loading={comment.isPending}
                onClick={() => comment.mutate({ instanceId: instance.id, comment: note }, { onError: fail })}
              >
                Save note
              </Button>
            </div>
          )}
        </section>

        {!readOnly ? (
          <footer className="flex flex-wrap items-center gap-3 rounded-card border border-border2 bg-surface p-4">
            <Button
              variant="primary"
              disabled={missing.size > 0}
              loading={complete.isPending}
              onClick={() => complete.mutate(instance.id, { onError: fail })}
            >
              Complete
            </Button>
            {missing.size > 0 ? (
              <p className="text-xs text-text3">Still to do: {missingLabels.join(', ')}</p>
            ) : (
              <p className="text-xs text-text3">Everything required is answered.</p>
            )}
          </footer>
        ) : null}
      </div>
    </div>
  )
}
