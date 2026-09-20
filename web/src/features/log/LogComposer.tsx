import { useRef, useState, type FormEvent } from 'react'
import { useCreateLogEntry, useLogMentionables } from '../../api/hooks/log'
import { useDepartments } from '../../api/hooks/users'
import type { LogEntryOut } from '../../api/types'
import { Button } from '../../components/ui'
import { MentionInput, TOKEN_RE, type MentionRef } from './MentionInput'

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

export function LogComposer({ onPosted }: { onPosted?: (entry: LogEntryOut) => void }) {
  const { data: mentionables } = useLogMentionables()
  const { data: departments } = useDepartments()
  const create = useCreateLogEntry()

  const [body, setBody] = useState('')
  const [mentions, setMentions] = useState<MentionRef[]>([])
  const [departmentId, setDepartmentId] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [requiresAck, setRequiresAck] = useState(false)
  const [audienceText, setAudienceText] = useState('')
  const [audienceMentions, setAudienceMentions] = useState<MentionRef[]>([])
  const fileInput = useRef<HTMLInputElement>(null)

  function toggleRequiresAck(checked: boolean) {
    setRequiresAck(checked)
    if (!checked) {
      // Otherwise a re-check later would submit whatever audience was picked before the
      // person changed their mind, rather than starting clean.
      setAudienceText('')
      setAudienceMentions([])
    }
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
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!body.trim() || create.isPending) return
    create.mutate(
      {
        body,
        departmentId: departmentId || undefined,
        mentions: pruneMentions(body, mentions),
        requiresAck,
        ackAudience: requiresAck ? pruneMentions(audienceText, audienceMentions) : undefined,
        photo: photo ?? undefined,
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

      <MentionInput
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
        disabled={create.isPending || !body.trim()}
      >
        Post
      </Button>
    </form>
  )
}
