import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useSession } from '../../auth/SessionContext'
import type { ConversationFilter } from '../../api/hooks/conversations'
import { useConversations } from '../../api/hooks/conversations'
import { ConversationList } from './ConversationList'
import { FilterTabs } from './FilterTabs'
import { EmptyState } from '../../components/ui'
import { ConversationView } from './ConversationView'

export function InboxPage() {
  const { id } = useParams<{ id: string }>()
  const { can } = useSession()
  // dept_staff cannot see the whole property, so their queue starts at Mine.
  const [filter, setFilter] = useState<ConversationFilter>(
    can('view_all_conversations') ? 'all' : 'mine',
  )

  // Counts for the tabs: the active filter's own length, plus the cheap always-on ones.
  const active = useConversations(filter)
  const counts = { [filter]: active.data?.pages.flat().length } as Partial<
    Record<ConversationFilter, number>
  >

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <FilterTabs value={filter} counts={counts} onChange={setFilter} />
      </div>
      <div className="flex min-h-0 flex-1">
        <div
          className={`w-full overflow-y-auto border-r border-border md:w-[360px] md:flex-none ${
            id ? 'hidden md:block' : ''
          }`}
        >
          <ConversationList filter={filter} selectedId={id} />
        </div>
        <div className={`min-w-0 flex-1 ${id ? '' : 'hidden md:block'}`}>
          {id ? (
            <ConversationView conversationId={id} />
          ) : (
            <EmptyState title="Pick a conversation" hint="Choose a row to read the thread." />
          )}
        </div>
      </div>
    </div>
  )
}
