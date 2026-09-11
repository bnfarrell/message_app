import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, propertyPath, type ApiError } from '../../api/client'
import { qk } from '../../api/queryKeys'
import type { ConversationDetail, DraftPromptOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button } from '../../components/ui'

function useDismissPrompt(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<void, ApiError, { promptId: string }>({
    mutationFn: ({ promptId }) =>
      api<void>(
        propertyPath(propertyId, `conversations/${conversationId}/draft-prompts/${promptId}/dismiss`),
        { method: 'POST' },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
    },
  })
}

export function DraftPromptBanner({
  conversation,
  onUseDraft,
}: {
  conversation: ConversationDetail
  onUseDraft: (prompt: DraftPromptOut) => void
}) {
  const dismiss = useDismissPrompt(conversation.id)
  const { can } = useSession()
  const pending = conversation.draftPrompts.filter((p) => p.status === 'pending')
  // Both buttons hit routes gated on `reply` (the dismiss route included), so a role
  // that cannot reply must not be offered them — the click would 403.
  if (pending.length === 0 || !can('reply')) return null

  const guestName = conversation.guest.firstName ?? 'the guest'
  const room = conversation.stay?.roomNumber

  return (
    <div className="flex flex-col gap-2 px-3 pt-3">
      {pending.map((prompt) => (
        <div
          key={prompt.id}
          data-testid="draft-prompt"
          className="flex flex-wrap items-center gap-3 rounded-card border border-okBorder bg-okBg px-3.5 py-3 text-sm text-okText"
        >
          <p className="min-w-0 flex-1">
            Work order <span className="font-mono font-bold">#{prompt.workOrderId}</span> (
            {prompt.workOrderTitle}
            {room ? `, ${room}` : ''}) is complete. Let {guestName} know?
          </p>
          <Button variant="primary" onClick={() => onUseDraft(prompt)}>
            Use draft
          </Button>
          <Button onClick={() => dismiss.mutate({ promptId: prompt.id })}>Dismiss</Button>
        </div>
      ))}
    </div>
  )
}
