import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useSetLogPinned } from '../../api/hooks/log'
import type { LogEntryOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Avatar, Badge, Button } from '../../components/ui'
import { relativeTime } from '../../lib/time'
import { AckBar } from './AckBar'
import { TOKEN_RE } from './MentionInput'
import { formatFieldValue } from './templates'

/**
 * Splits on `TOKEN_RE` via `matchAll`, which never touches the shared regex's own
 * `lastIndex` — using `.exec()`/`.test()` on the module-level instance here would leave
 * `lastIndex` set after the first entry and silently miss mentions on the next one.
 */
function renderBody(body: string): ReactNode[] {
  const parts: ReactNode[] = []
  let cursor = 0
  let key = 0
  for (const match of body.matchAll(TOKEN_RE)) {
    const index = match.index ?? 0
    if (index > cursor) parts.push(body.slice(cursor, index))
    parts.push(
      <span key={key++} className="font-semibold text-accent">
        {match[1]}
      </span>,
    )
    cursor = index + match[0].length
  }
  if (cursor < body.length) parts.push(body.slice(cursor))
  return parts
}

export function LogEntryCard({ entry }: { entry: LogEntryOut }): JSX.Element {
  const { can } = useSession()
  const setPinned = useSetLogPinned()

  const fieldValues = entry.fieldValues ?? []
  const text = fieldValues.length > 0 ? entry.notes ?? '' : entry.body

  return (
    <article className="flex flex-col gap-2 rounded-card border border-border2 bg-surface px-3 pb-2.5 pt-3">
      <div className="flex items-center gap-2">
        <Avatar name={entry.authorName} size={26} />
        <span className="text-sm font-semibold">{entry.authorName}</span>
        <span className="font-mono text-xs text-text3">{relativeTime(entry.createdAt)}</span>
        <Badge>{entry.shift.toUpperCase()}</Badge>
        {entry.departmentName ? <Badge tone="neutral">{entry.departmentName}</Badge> : null}
        {entry.template ? <Badge tone="note">{entry.template.name}</Badge> : null}
        {can('pin_log_entry') ? (
          <Button
            variant="ghost"
            className="ml-auto"
            loading={setPinned.isPending}
            onClick={() => setPinned.mutate({ id: entry.id, pinned: !entry.pinned })}
          >
            {entry.pinned ? 'Unpin' : 'Pin'}
          </Button>
        ) : null}
      </div>

      {fieldValues.length > 0 ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {fieldValues.map((value) => (
            <Fragment key={value.fieldId}>
              <dt className="text-text3">{value.label}</dt>
              <dd className="whitespace-pre-wrap font-mono">{formatFieldValue(value)}</dd>
            </Fragment>
          ))}
        </dl>
      ) : null}

      {/* A templated post's body repeats its values as text; the card shows the table above
          and only the author's notes here (spec §4.2). */}
      {text ? <p className="whitespace-pre-wrap text-sm">{renderBody(text)}</p> : null}

      {entry.photoUrl ? (
        <img src={entry.photoUrl} alt="Attached" className="max-h-60 rounded" />
      ) : null}

      {entry.linkedWorkOrderId ? (
        <Link to={`/app/work-orders/${entry.linkedWorkOrderId}`} className="text-xs font-semibold text-accent">
          View work order
        </Link>
      ) : null}
      {entry.linkedConversationId ? (
        <Link to={`/app/inbox/${entry.linkedConversationId}`} className="text-xs font-semibold text-accent">
          View conversation
        </Link>
      ) : null}

      <AckBar entry={entry} />
    </article>
  )
}
