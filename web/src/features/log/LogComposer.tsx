import { useRef, useState, type FormEvent } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreateLogEntry, useLogMentionables, useLogTemplates } from '../../api/hooks/log'
import { useDepartments } from '../../api/hooks/users'
import type { LogEntryOut, LogFieldValueIn, LogTemplateFieldOut, LogTemplateOut } from '../../api/types'
import { Button, Input, Textarea } from '../../components/ui'
import { MentionInput, TOKEN_RE, type MentionRef } from './MentionInput'
import { NUMERIC_FIELD_TYPES } from './templates'

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']
const FIELD = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT =
  'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

/**
 * A pick records a `MentionRef` immediately, but nothing removes it if the user then
 * deletes the token text it points at — so a stale mention would still ride along and
 * notify someone about an entry that no longer mentions them (Task 10 review defect).
 * Filtering against the tokens still present in `text` at submit time closes that gap.
 */
function pruneMentions(text: string, mentions: MentionRef[]): MentionRef[] {
  const present = new Set<string>()
  for (const match of text.matchAll(TOKEN_RE)) {
    present.add(`${match[2]}:${match[3]}`)
  }
  return mentions.filter((m) => present.has(`${m.type}:${m.id}`))
}

/** Answers by field id, exactly as typed; blank means unanswered, as on the server. */
type Answers = Record<string, string>

function answered(answers: Answers, field: LogTemplateFieldOut): boolean {
  return (answers[field.id] ?? '').trim() !== ''
}

/** A number that parses goes over as a JSON number; anything else goes over as typed, so the
 *  server can name what is wrong with it (`not_a_number`) rather than the client guessing. */
function toFieldValues(template: LogTemplateOut, answers: Answers): LogFieldValueIn[] {
  return template.fields.filter((f) => answered(answers, f)).map((f) => {
    const raw = answers[f.id]!.trim()
    const number = Number(raw)
    return { fieldId: f.id, value: NUMERIC_FIELD_TYPES.has(f.fieldType) && Number.isFinite(number) ? number : raw }
  })
}

function TemplateField({ field, value, error, onChange }: {
  field: LogTemplateFieldOut
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  const id = `log-field-${field.id}`
  const common = { id, value, 'aria-required': field.required, 'aria-invalid': Boolean(error) }
  return (
    <div>
      <label className={FIELD} htmlFor={id}>
        {field.label}
        {field.required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {field.fieldType === 'long_text' ? (
        <Textarea {...common} rows={3} onChange={(e) => onChange(e.target.value)} />
      ) : field.fieldType === 'short_text' ? (
        <Input {...common} maxLength={200} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <div className="flex items-center gap-2">
          <Input
            {...common}
            inputMode={field.fieldType === 'integer' ? 'numeric' : 'decimal'}
            onChange={(e) => onChange(e.target.value)}
          />
          {field.fieldType === 'percent' ? <span className="text-sm text-text3">%</span> : null}
        </div>
      )}
      {error ? <p className="mt-1 text-xs text-dangerText">{error}</p> : null}
    </div>
  )
}

export function LogComposer({ onPosted }: { onPosted?: (entry: LogEntryOut) => void }) {
  const { data: mentionables } = useLogMentionables()
  const { data: departments } = useDepartments()
  const { data: templates } = useLogTemplates()
  const create = useCreateLogEntry()

  const [body, setBody] = useState('')
  const [mentions, setMentions] = useState<MentionRef[]>([])
  const [departmentId, setDepartmentId] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [requiresAck, setRequiresAck] = useState(false)
  const [audienceText, setAudienceText] = useState('')
  const [audienceMentions, setAudienceMentions] = useState<MentionRef[]>([])
  const [templateId, setTemplateId] = useState('')
  const [answers, setAnswers] = useState<Answers>({})
  const fileInput = useRef<HTMLInputElement>(null)

  const available = templates ?? []
  const template = available.find((t) => t.id === templateId)
  // The picker refetches after a 400 naming `inactive`/`unknown_field` (useCreateLogEntry), so a
  // template that was deactivated or lost its audience while the form sat open disappears from
  // `templates` out from under the still-selected id. Falling back to a free-form post here would
  // send it silently under the vanished template's name (final review finding 4).
  const templateVanished = templateId !== '' && templates !== undefined && !template
  const fields = fieldErrors(create.error)
  const ready = template
    ? template.fields.every((f) => !f.required || answered(answers, f))
      && (template.fields.some((f) => answered(answers, f)) || body.trim() !== '')
    : templateVanished
      ? false
      : body.trim() !== ''

  function toggleRequiresAck(checked: boolean) {
    setRequiresAck(checked)
    if (!checked) {
      // Otherwise a re-check later would submit whatever audience was picked before the
      // person changed their mind, rather than starting clean.
      setAudienceText('')
      setAudienceMentions([])
    }
  }

  function chooseTemplate(id: string) {
    // "No template" clears the form; switching templates starts the new one blank.
    setTemplateId(id)
    setAnswers({})
    create.reset()
  }

  function clearPhoto() {
    setPhoto(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  function reset() {
    setBody('')
    setMentions([])
    setDepartmentId('')
    clearPhoto()
    setRequiresAck(false)
    setAudienceText('')
    setAudienceMentions([])
    setTemplateId('')
    setAnswers({})
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!ready || create.isPending) return
    create.mutate(
      {
        body,
        departmentId: departmentId || undefined,
        mentions: pruneMentions(body, mentions),
        requiresAck,
        ackAudience: requiresAck ? pruneMentions(audienceText, audienceMentions) : undefined,
        photo: photo ?? undefined,
        ...(template ? { templateId: template.id, fieldValues: toFieldValues(template, answers) } : {}),
      },
      { onSuccess: (entry) => { reset(); onPosted?.(entry) } },
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 border-t border-border p-3">
      {create.error ? (
        <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {create.error.message}
        </p>
      ) : null}
      {templateVanished ? (
        <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          This template is no longer available — pick another or post without one
        </p>
      ) : null}

      {available.length > 0 || templateVanished ? (
        <div>
          <label className={FIELD} htmlFor="log-template">Use a template</label>
          <select
            id="log-template"
            className={SELECT}
            value={templateId}
            onChange={(event) => chooseTemplate(event.target.value)}
          >
            <option value="">No template</option>
            {/* Keeps the controlled value matched to a real option: without this, a vanished
                id matches nothing, so the browser shows "No template" as selected even though
                templateId (and so templateVanished) still points at the old one. */}
            {templateVanished ? <option value={templateId} disabled>(no longer available)</option> : null}
            {available.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
      ) : null}

      {template ? (
        <div className="grid grid-cols-2 gap-3">
          {template.fields.map((field) => (
            <div key={field.id} className={field.fieldType === 'long_text' ? 'col-span-2' : undefined}>
              <TemplateField
                field={field}
                value={answers[field.id] ?? ''}
                error={fields[field.id]}
                onChange={(value) => setAnswers({ ...answers, [field.id]: value })}
              />
            </div>
          ))}
        </div>
      ) : null}

      {template ? <label className={FIELD} htmlFor="log-body">Notes (optional)</label> : null}
      <MentionInput
        id="log-body"
        value={body}
        mentions={mentions}
        options={mentionables ?? []}
        onChange={(value, next) => { setBody(value); setMentions(next) }}
        placeholder="Add to the log…"
      />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={FIELD} htmlFor="log-department">Department</label>
          <select
            id="log-department"
            className={SELECT}
            value={departmentId}
            onChange={(event) => setDepartmentId(event.target.value)}
          >
            <option value="">No department</option>
            {(departments ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={FIELD} htmlFor="log-photo">Photo</label>
          <input
            ref={fileInput}
            id="log-photo"
            type="file"
            accept={ACCEPTED.join(',')}
            onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
            className="block w-full text-xs text-text3"
          />
          {photo ? (
            <p className="mt-1 flex items-center gap-2 text-xs text-text3">
              {photo.name}
              <button type="button" onClick={clearPhoto} className="font-semibold underline">
                Clear
              </button>
            </p>
          ) : null}
        </div>
      </div>

      <label className="flex items-center gap-2 text-xs font-semibold text-text3">
        <input
          type="checkbox"
          checked={requiresAck}
          onChange={(event) => toggleRequiresAck(event.target.checked)}
        />
        Requires acknowledgement
      </label>

      {requiresAck ? (
        <MentionInput
          value={audienceText}
          mentions={audienceMentions}
          options={mentionables ?? []}
          onChange={(value, next) => { setAudienceText(value); setAudienceMentions(next) }}
          placeholder="Who needs to acknowledge this?"
        />
      ) : null}

      <Button
        type="submit"
        variant="primary"
        className="self-end"
        loading={create.isPending}
        disabled={create.isPending || !ready}
      >
        Post
      </Button>
    </form>
  )
}
