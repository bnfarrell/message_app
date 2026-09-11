import { useEffect, useRef, useState } from 'react'
import { useQuickReplies, useRenderQuickReply } from '../../api/hooks/content'
import { useSendMessage } from '../../api/hooks/conversations'
import { useRealtime } from '../../api/ws'
import { useSession } from '../../auth/SessionContext'
import type { ConversationDetail } from '../../api/types'
import { Button, Textarea } from '../../components/ui'
import { cn } from '../../lib/cn'
import { charCount, segmentCount } from '../../lib/segments'
import { AssetPicker } from './AssetPicker'
import { QuickReplyPalette } from './QuickReplyPalette'

export function Composer({
  conversationId,
  conversation,
  draftBody,
  draftPromptId: draftPromptIdIn,
  onDraftConsumed,
}: {
  conversationId: string
  conversation: ConversationDetail
  draftBody?: string
  draftPromptId?: string | null
  onDraftConsumed?: () => void
}) {
  const { can } = useSession()
  const [body, setBody] = useState('')
  const [assetId, setAssetId] = useState<string | null>(null)
  const [draftPromptId, setDraftPromptId] = useState<string | null>(null)
  // Escape hides the palette without touching the draft; typing again reopens it.
  const [paletteDismissed, setPaletteDismissed] = useState(false)
  const box = useRef<HTMLTextAreaElement>(null)
  const send = useSendMessage(conversationId)
  const { data: replies } = useQuickReplies()
  const render = useRenderQuickReply()
  const { setPresence } = useRealtime()

  // A draft handed down from the prompt banner (Task 15) loads once, then clears.
  // This must be an effect, not a render-phase setState — the latter loops.
  useEffect(() => {
    if (draftBody) {
      setBody(draftBody)
      setDraftPromptId(draftPromptIdIn ?? null)
      box.current?.focus()
      onDraftConsumed?.()
    }
  }, [draftBody, draftPromptIdIn, onDraftConsumed])

  // The palette opens only when '/' starts the draft — 'either/or' must not trigger it.
  const paletteOpen =
    body.startsWith('/') && !body.includes(' ') && !body.includes('\n') && !paletteDismissed
  const segments = segmentCount(body)
  const characters = charCount(body)
  const optedOut = conversation.guest.smsConsentStatus === 'opted_out'

  function submit() {
    const trimmed = body.trim()
    if (!trimmed || send.isPending) return
    send.mutate(
      {
        body: trimmed,
        digitalAssetId: assetId,
        draftPromptId,
      },
      {
        onError: () => setBody(trimmed), // give the text back; retyping is the real cost
      },
    )
    setBody('')
    setAssetId(null)
    setDraftPromptId(null)
  }

  // A role without `reply` (e.g. corporate) legitimately reaches the thread but must get
  // it read-only — no textarea, no send button, no quick-reply palette. `add_note` is a
  // separate capability and is not gated here.
  if (!can('reply')) return null

  return (
    <div className="border-t border-border p-3">
      {optedOut ? (
        <p className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          This guest has opted out of SMS. A send will be rejected unless they text START.
        </p>
      ) : null}

      {send.error ? (
        <p role="alert" className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {send.error.message}
        </p>
      ) : null}

      <div className="relative">
        {paletteOpen && replies ? (
          <QuickReplyPalette
            replies={replies}
            term={body}
            onClose={() => setPaletteDismissed(true)}
            onPick={(reply) => {
              // The server interpolates; we never substitute tokens client-side.
              render.mutate(
                { id: reply.id, conversationId },
                {
                  onSuccess: (rendered) => {
                    setBody(rendered.body)
                    box.current?.focus()
                  },
                },
              )
            }}
          />
        ) : null}

        <Textarea
          ref={box}
          rows={3}
          value={body}
          placeholder="Type a reply, or / for a quick reply"
          onChange={(event) => {
            setBody(event.target.value)
            setPaletteDismissed(false)
          }}
          onFocus={() => setPresence(conversationId, 'composing')}
          onBlur={() => setPresence(conversationId, 'viewing')}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
              event.preventDefault()
              submit()
            }
          }}
        />
      </div>

      <div className="mt-2 flex items-center gap-3">
        <AssetPicker
          onPick={(asset) => {
            setAssetId(asset.id)
            setBody((current) => `${current}${current ? ' ' : ''}${window.location.origin}/a/${asset.shortCode}`)
          }}
        />
        {segments > 0 ? (
          <span
            data-testid="segment-counter"
            className={cn(
              'font-mono text-xs',
              segments > 4 ? 'text-dangerText' : segments > 1 ? 'text-warnText' : 'text-text3',
            )}
          >
            {characters} chars · {segments} segment{segments === 1 ? '' : 's'}
          </span>
        ) : null}
        <Button
          variant="primary"
          className="ml-auto"
          loading={send.isPending}
          onClick={submit}
          title="Ctrl+Enter"
        >
          Send
        </Button>
      </div>
    </div>
  )
}
