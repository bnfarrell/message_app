import { useStaffConversations } from '../../api/hooks/staffMessages'
import { Avatar, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'

function relativeTime(iso: string | null): string {
  if (!iso) return ''
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'a few seconds ago'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export function ConversationList({
  selectedId,
  onSelect,
}: {
  selectedId?: string
  onSelect: (id: string) => void
}) {
  const { data, isPending, error } = useStaffConversations()

  if (isPending) {
    return (
      <div className="grid place-items-center p-8">
        <Spinner />
      </div>
    )
  }
  if (error) return <EmptyState title="Could not load conversations" hint={error.message} />
  if (!data || data.length === 0) {
    return <EmptyState title="No conversations yet" hint="Start one from the list below." />
  }

  return (
    <ul className="flex flex-col">
      {data.map((conv) => (
        <li key={conv.id}>
          <button
            type="button"
            onClick={() => onSelect(conv.id)}
            aria-current={conv.id === selectedId ? 'true' : undefined}
            className={cn(
              'flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left',
              conv.id === selectedId ? 'bg-sel' : 'hover:bg-surface2',
            )}
          >
            <Avatar name={conv.displayName} tone={conv.kind === 'all' ? 'accent' : 'muted'} />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="truncate text-sm font-semibold">{conv.displayName}</span>
                {conv.lastMessageAt ? (
                  <span className="flex-none text-[11px] text-text3">
                    {relativeTime(conv.lastMessageAt)}
                  </span>
                ) : null}
              </span>
              <span className="block truncate text-[13px] text-text3">
                {conv.lastMessagePreview ?? 'No message sent'}
              </span>
            </span>
            {conv.unread ? (
              <span
                data-testid="unread-dot"
                aria-label="Unread"
                className="h-2 w-2 flex-none rounded-full bg-accent"
              />
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  )
}
