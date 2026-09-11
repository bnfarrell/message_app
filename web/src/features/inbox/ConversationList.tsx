import { Link } from 'react-router-dom'
import { useConversations, type ConversationFilter } from '../../api/hooks/conversations'
import { useStaff } from '../../api/hooks/users'
import { useRealtime } from '../../api/ws'
import type { ConversationSummary } from '../../api/types'
import { SlaChip } from '../../components/SlaChip'
import { Avatar, Badge, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'

function guestLabel(conversation: ConversationSummary): string {
  const { firstName, lastName, phoneE164 } = conversation.guest
  const name = [firstName, lastName].filter(Boolean).join(' ')
  return name || phoneE164
}

function Row({
  conversation,
  selected,
  assigneeName,
}: {
  conversation: ConversationSummary
  selected: boolean
  assigneeName: string | null
}) {
  const { presence } = useRealtime()
  const watchers = (presence[conversation.id] ?? []).filter((u) => u.state !== 'composing')
  const answered = !conversation.unanswered
  const preview = conversation.lastMessagePreview ?? ''

  return (
    <Link
      to={`/app/inbox/${conversation.id}`}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'flex min-h-[44px] items-center gap-3.5 border-b border-border px-4 py-3.5',
        selected ? 'bg-sel shadow-[inset_3px_0_0_var(--accent)]' : 'hover:bg-surface2',
      )}
    >
      <SlaChip
        dueAt={conversation.slaDueAt}
        startAt={conversation.lastGuestMessageAt}
        answered={answered}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span data-testid="row-room" className="font-mono text-sm font-semibold text-roomNum">
            {conversation.roomNumber ?? '—'}
          </span>
          <span className="truncate text-sm font-semibold">{guestLabel(conversation)}</span>
          {!conversation.roomNumber ? <Badge>New</Badge> : null}
          {conversation.guest.smsConsentStatus === 'opted_out' ? (
            <Badge tone="danger" className="text-dangerText">
              Opted out
            </Badge>
          ) : null}
          {assigneeName ? (
            <Avatar name={assigneeName} size={22} tone="muted" />
          ) : (
            <Badge>Unassigned</Badge>
          )}
        </div>
        <p className={cn('truncate text-[13px]', answered ? 'text-text3' : 'text-text2')}>
          {answered && conversation.lastStaffMessageAt ? `You: ${preview}` : preview}
        </p>
      </div>
      {watchers.length > 0 ? (
        <div className="flex flex-none -space-x-1.5">
          {watchers.slice(0, 3).map((u) => (
            <Avatar key={u.id} name={u.firstName} size={22} tone="presence" />
          ))}
        </div>
      ) : null}
    </Link>
  )
}

export function ConversationList({
  filter,
  selectedId,
  dept,
}: {
  filter: ConversationFilter
  selectedId?: string
  dept?: string | null
}) {
  const query = useConversations(filter, dept)
  const { data: staff } = useStaff()
  const rows = query.data?.pages.flat() ?? []

  if (query.isPending) {
    return (
      <div className="grid place-items-center p-10">
        <Spinner />
      </div>
    )
  }
  if (query.error) {
    return <EmptyState title="Could not load the queue" hint={query.error.message} />
  }
  if (rows.length === 0) {
    return <EmptyState title="Nothing waiting" hint="No conversations match this filter." />
  }

  const nameFor = (userId: string | null | undefined): string | null => {
    if (!userId) return null
    const person = staff?.find((s) => s.id === userId)
    return person ? `${person.firstName} ${person.lastName}` : null
  }

  return (
    <div className="flex flex-col">
      {/* The server orders by unanswered-then-oldest; rendering as received is deliberate. */}
      {rows.map((conversation) => (
        <Row
          key={conversation.id}
          conversation={conversation}
          selected={conversation.id === selectedId}
          assigneeName={nameFor(conversation.assignedUserId)}
        />
      ))}
      {query.hasNextPage ? (
        <button
          onClick={() => void query.fetchNextPage()}
          disabled={query.isFetchingNextPage}
          className="h-11 border-b border-border text-sm font-semibold text-text3 hover:text-text"
        >
          {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      ) : null}
    </div>
  )
}
