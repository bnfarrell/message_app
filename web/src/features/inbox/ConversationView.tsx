import { useEffect, useMemo, useState } from 'react'
import { useConversation, useRetryMessage } from '../../api/hooks/conversations'
import { useStaff } from '../../api/hooks/users'
import { useRealtime } from '../../api/ws'
import type { MessageOut, NoteOut } from '../../api/types'
import { EmptyState, Spinner } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { Composer } from './Composer'
import { ConversationHeader } from './ConversationHeader'
import { DraftPromptBanner } from './DraftPromptBanner'
import { GuestPanel } from './GuestPanel'
import { MessageBubble } from './MessageBubble'

type Entry =
  | { kind: 'message'; at: string; message: MessageOut }
  | { kind: 'note'; at: string; note: NoteOut }

export function ConversationView({ conversationId }: { conversationId: string }) {
  const { data, isPending, error } = useConversation(conversationId)
  const { data: staff } = useStaff()
  const { setPresence } = useRealtime()
  const retry = useRetryMessage(conversationId)
  const [draft, setDraft] = useState<{ body: string; promptId: string } | null>(null)

  // Tell everyone else we are on this conversation; clear it on the way out.
  useEffect(() => {
    setPresence(conversationId, 'viewing')
    return () => setPresence(null, 'viewing')
  }, [conversationId, setPresence])

  const timeline = useMemo<Entry[]>(() => {
    if (!data) return []
    const entries: Entry[] = [
      // A queued message has no sentAt yet; sort it last so it appears where it was typed.
      ...data.messages.map((m) => ({ kind: 'message' as const, at: m.sentAt ?? '9999', message: m })),
      ...data.notes.map((n) => ({ kind: 'note' as const, at: n.createdAt, note: n })),
    ]
    return entries.sort((a, b) => a.at.localeCompare(b.at))
  }, [data])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !data) {
    return <EmptyState title="Could not open this conversation" hint={error?.message} />
  }

  const nameFor = (userId: string | null | undefined): string | null => {
    if (!userId) return null
    const person = staff?.find((s) => s.id === userId)
    return person?.firstName ?? null
  }

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <ConversationHeader conversation={data} />
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          {timeline.map((entry) =>
            entry.kind === 'message' ? (
              <MessageBubble
                key={entry.message.id}
                message={entry.message}
                authorName={nameFor(entry.message.authorUserId)}
                onRetry={
                  entry.message.deliveryStatus === 'failed' ||
                  entry.message.deliveryStatus === 'undelivered'
                    ? () => retry.mutate({ messageId: entry.message.id })
                    : undefined
                }
              />
            ) : (
              <div
                key={entry.note.id}
                data-testid="note"
                className="rounded-card border border-noteBorder bg-noteBg px-3.5 py-3 text-sm text-noteText"
              >
                <p className="mb-1 flex items-center gap-2 text-xs font-bold uppercase tracking-wide">
                  <span className="text-noteIcon">●</span>
                  Internal
                  <span className="font-normal text-noteText/70">
                    {entry.note.authorName} · {formatClock(entry.note.createdAt)}
                  </span>
                </p>
                {entry.note.body}
              </div>
            ),
          )}
        </div>
        <DraftPromptBanner
          conversation={data}
          onUseDraft={(prompt) => setDraft({ body: prompt.body, promptId: prompt.id })}
        />
        <Composer
          conversationId={conversationId}
          conversation={data}
          draftBody={draft?.body}
          draftPromptId={draft?.promptId}
          onDraftConsumed={() => setDraft(null)}
        />
      </div>
      <GuestPanel conversation={data} />
    </div>
  )
}
