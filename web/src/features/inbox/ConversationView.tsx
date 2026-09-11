import { useConversation } from '../../api/hooks/conversations'
import { Spinner } from '../../components/ui'

/**
 * Scoped stub for Task 12: just enough for InboxPage to compile and the three-column
 * layout to be verifiable. Task 13 replaces this with the real thread view.
 */
export function ConversationView({ conversationId }: { conversationId: string }) {
  const { data, isPending } = useConversation(conversationId)

  if (isPending) {
    return (
      <div className="grid place-items-center p-10">
        <Spinner />
      </div>
    )
  }

  const name = [data?.guest.firstName, data?.guest.lastName].filter(Boolean).join(' ')
  return <div className="p-4 text-sm font-semibold">{name || data?.guest.phoneE164}</div>
}
