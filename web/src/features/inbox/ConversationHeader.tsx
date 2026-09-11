import { Link } from 'react-router-dom'
import type { ConversationDetail } from '../../api/types'
import { useRealtime } from '../../api/ws'
import { useSession } from '../../auth/SessionContext'
import { SlaChip } from '../../components/SlaChip'
import { Badge } from '../../components/ui'
import { ConversationActions } from './ConversationActions'

/** Exported for its own unit test — the copy is the spec (§5.3), not an implementation detail. */
export function presenceLine(names: string[], composing: boolean): string {
  const verb = composing ? 'replying' : 'viewing'
  if (names.length === 0) return ''
  if (names.length === 1) return `${names[0]} is ${verb}`
  return `${names[0]} and ${names.length - 1} other${names.length > 2 ? 's' : ''} are ${verb}`
}

export function ConversationHeader({ conversation }: { conversation: ConversationDetail }) {
  const { presence } = useRealtime()
  const { user } = useSession()
  const { guest, stay } = conversation
  const others = (presence[conversation.id] ?? []).filter((u) => u.id !== user.id)
  const composing = others.some((u) => u.state === 'composing')
  const name = [guest.firstName, guest.lastName].filter(Boolean).join(' ') || guest.phoneE164

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
      {/* §5.2: below md the list is hidden and this thread is the only pane — the only
          way back is otherwise the browser button. Hidden at md+, where the list is
          visible alongside the thread and back navigation is redundant. */}
      <Link
        to="/app/inbox"
        className="flex items-center gap-1 text-sm font-semibold text-text3 hover:text-text md:hidden"
      >
        ← Back
      </Link>
      <span className="font-mono text-xl font-bold text-roomNum">{stay?.roomNumber ?? '—'}</span>
      <div className="min-w-0">
        <p className="truncate text-sm font-bold">{name}</p>
        <p className="text-xs uppercase tracking-wide text-text3">
          {[
            conversation.channelPrimary.toUpperCase(),
            guest.loyaltyTier?.toUpperCase(),
            stay ? `${stay.stayCount}TH STAY` : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </p>
      </div>
      <div className="ml-auto flex items-center gap-2">
        {others.length > 0 ? (
          <Badge tone="presence">{presenceLine(others.map((u) => u.firstName), composing)}</Badge>
        ) : null}
        {guest.smsConsentStatus === 'opted_out' ? <Badge tone="danger">Opted out</Badge> : null}
        <SlaChip
          dueAt={conversation.slaDueAt}
          startAt={conversation.lastGuestMessageAt}
          answered={!conversation.lastGuestMessageAt || Boolean(
            conversation.lastStaffMessageAt &&
              conversation.lastStaffMessageAt > conversation.lastGuestMessageAt,
          )}
        />
        <ConversationActions conversation={conversation} />
      </div>
    </header>
  )
}
