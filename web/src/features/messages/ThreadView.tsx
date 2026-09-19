import { useEffect, useRef, useState } from 'react'
import {
  useMarkStaffConversationRead,
  useSendStaffMessage,
  useStaffConversation,
} from '../../api/hooks/staffMessages'
import { Avatar, Button, EmptyState, Spinner } from '../../components/ui'
import { formatClock } from '../../lib/time'

const MAX_BYTES = 8 * 1024 * 1024 // server's staff_messages MAX_PHOTO_BYTES (work_orders.MAX_PHOTO_BYTES)
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']

export function ThreadView({
  conversationId,
  onManageGroup,
}: {
  conversationId: string
  onManageGroup?: () => void
}) {
  const { data, isPending, error } = useStaffConversation(conversationId)
  const send = useSendStaffMessage(conversationId)
  const markRead = useMarkStaffConversationRead(conversationId)
  const [draft, setDraft] = useState('')
  const [clientError, setClientError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    markRead.mutate()
    // Only when the conversation identity changes — marking read on every unrelated
    // re-render would spam the endpoint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !data) return <EmptyState title="Could not load this conversation" hint={error?.message} />

  function submitText(event: React.FormEvent) {
    event.preventDefault()
    const body = draft.trim()
    if (!body) return
    send.mutate({ body }, { onSuccess: () => setDraft('') })
  }

  function onFile(file: File | undefined) {
    if (!file) return
    if (!ACCEPTED.includes(file.type)) {
      setClientError('Only JPEG, PNG or WebP photos are accepted.')
      return
    }
    if (file.size > MAX_BYTES) {
      setClientError('That photo is over 8 MB. Choose a smaller one.')
      return
    }
    setClientError(null)
    send.mutate(
      { photo: file },
      {
        onSuccess: () => {
          if (fileInput.current) fileInput.current.value = ''
        },
      },
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Avatar name={data.displayName} tone={data.kind === 'all' ? 'accent' : 'muted'} />
        <h2 className="text-sm font-bold">{data.displayName}</h2>
        {data.kind === 'group' && onManageGroup ? (
          <Button className="ml-auto" onClick={onManageGroup}>
            Group
          </Button>
        ) : null}
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4">
        {data.messages.length === 0 ? (
          <p className="m-auto text-xs text-text3">This is beginning of your conversation.</p>
        ) : (
          data.messages.map((message) => (
            <div key={message.id} className="max-w-[70%]">
              <p className="text-[11px] text-text3">
                {message.authorName} · {formatClock(message.createdAt)}
              </p>
              {message.body ? <p className="text-sm">{message.body}</p> : null}
              {message.photoUrl ? (
                <img src={message.photoUrl} alt="Attached" className="mt-1 max-h-60 rounded" />
              ) : null}
            </div>
          ))
        )}
      </div>

      {clientError ? (
        <p role="alert" className="mx-4 mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {clientError}
        </p>
      ) : null}

      <form onSubmit={submitText} className="flex items-center gap-2 border-t border-border p-3">
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPTED.join(',')}
          aria-label="Attach photo"
          onChange={(event) => onFile(event.target.files?.[0])}
          className="hidden"
        />
        <Button
          type="button"
          variant="ghost"
          onClick={() => fileInput.current?.click()}
          disabled={send.isPending}
        >
          Photo
        </Button>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Type your message"
          disabled={send.isPending}
          className="h-10 flex-1 rounded border border-border3 bg-surface2 px-3 text-sm focus:border-accent focus:outline-none"
        />
        <Button type="submit" variant="primary" disabled={send.isPending || !draft.trim()}>
          Send
        </Button>
      </form>
    </div>
  )
}
