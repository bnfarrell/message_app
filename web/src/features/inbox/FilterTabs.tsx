import { useSession } from '../../auth/SessionContext'
import { cn } from '../../lib/cn'
import type { ConversationFilter } from '../../api/hooks/conversations'

const ALL_TABS: { value: ConversationFilter; label: string; needsAllAccess?: boolean }[] = [
  { value: 'all', label: 'All', needsAllAccess: true },
  { value: 'mine', label: 'Mine' },
  { value: 'unassigned', label: 'Unassigned', needsAllAccess: true },
  { value: 'overdue', label: 'Overdue' },
  { value: 'snoozed', label: 'Snoozed' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'archived', label: 'Archived' },
]

export function FilterTabs({
  value,
  counts,
  onChange,
}: {
  value: ConversationFilter
  counts: Partial<Record<ConversationFilter, number>>
  onChange: (filter: ConversationFilter) => void
}) {
  const { can } = useSession()
  const tabs = ALL_TABS.filter((t) => !t.needsAllAccess || can('view_all_conversations'))

  return (
    <div role="tablist" className="flex flex-wrap items-center gap-1.5">
      {tabs.map((tab) => {
        const count = counts[tab.value]
        return (
          <button
            key={tab.value}
            role="tab"
            aria-selected={value === tab.value}
            onClick={() => onChange(tab.value)}
            className={cn(
              'inline-flex h-11 items-center gap-2 rounded px-3.5 text-[13.5px] font-semibold md:h-9',
              value === tab.value ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
            )}
          >
            {tab.label}
            {/* Only render a count we actually have — a stale 0 reads as "nothing to do". */}
            {count === undefined ? null : <span className="font-mono text-xs opacity-85">{count}</span>}
          </button>
        )
      })}
    </div>
  )
}
