import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useCreateStaffConversation, useStaffConversations } from '../../api/hooks/staffMessages'
import { Button, EmptyState } from '../../components/ui'
import { ConversationList } from './ConversationList'
import { GroupPanel } from './GroupPanel'
import { NewConversationList } from './NewConversationList'
import { ThreadView } from './ThreadView'

export function MessagesPage() {
  const { id } = useParams<{ id?: string }>()
  const navigate = useNavigate()
  const { data: conversations } = useStaffConversations()
  const createDm = useCreateStaffConversation()
  const [creatingGroup, setCreatingGroup] = useState(false)
  const [managingGroupId, setManagingGroupId] = useState<string | null>(null)

  const dmPartnerIds = (conversations ?? [])
    .filter((conv) => conv.kind === 'dm' && conv.otherUserId)
    .map((conv) => conv.otherUserId as string)

  function startDm(userId: string) {
    createDm.mutate(
      { kind: 'dm', userId },
      { onSuccess: (conv) => navigate(`/app/messages/${conv.id}`) },
    )
  }

  function leaveGroup() {
    setManagingGroupId(null)
    navigate('/app/messages')
  }

  const managingGroup = conversations?.find((c) => c.id === managingGroupId)

  return (
    <div className="grid h-full min-h-0 grid-cols-[320px_1fr] divide-x divide-border">
      <div className="flex min-h-0 flex-col overflow-y-auto">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Messaging</h1>
          <Button onClick={() => setCreatingGroup(true)}>+ Group</Button>
        </header>

        {createDm.error ? (
          <p
            role="alert"
            className="mx-4 mt-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText"
          >
            {createDm.error.message}
          </p>
        ) : null}

        <div>
          <p className="px-4 pt-3 text-xs font-bold uppercase tracking-wide text-text3">
            Active Conversations
          </p>
          <ConversationList
            selectedId={id}
            onSelect={(conversationId) => navigate(`/app/messages/${conversationId}`)}
          />
          <p className="px-4 pt-4 text-xs font-bold uppercase tracking-wide text-text3">
            New Conversations
          </p>
          <NewConversationList excludeUserIds={dmPartnerIds} onStart={startDm} />
        </div>
      </div>

      <div className="min-h-0">
        {id ? (
          // Remounting ThreadView per conversation (via `key`) resets its internal state
          // (scroll position, composer draft) — without it, switching between two
          // conversations reuses the same instance since the route param alone changes.
          <ThreadView key={id} conversationId={id} onManageGroup={() => setManagingGroupId(id)} />
        ) : (
          <EmptyState
            title="Select a conversation"
            hint="Pick someone from the list, or start a new one."
          />
        )}
      </div>

      {creatingGroup ? <GroupPanel open onClose={() => setCreatingGroup(false)} /> : null}
      {managingGroup ? (
        <GroupPanel
          open
          onClose={() => setManagingGroupId(null)}
          existing={managingGroup}
          onSelfRemoved={leaveGroup}
        />
      ) : null}
    </div>
  )
}
