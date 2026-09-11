import { useEffect, useRef, useState } from 'react'
import { useQuickReplies, useRenderQuickReply } from '../../api/hooks/content'
import { useAddNote, useSendMessage } from '../../api/hooks/conversations'
import { useRealtime } from '../../api/ws'
import { useSession } from '../../auth/SessionContext'
import type { ConversationDetail } from '../../api/types'
import { Button, Textarea } from '../../components/ui'
import { cn } from '../../lib/cn'
import { charCount, segmentCount } from '../../lib/segments'
import { AssetPicker } from './AssetPicker'
import { CreateWorkOrderModal } from './CreateWorkOrderModal'
import { QuickReplyPalette } from './QuickReplyPalette'

type Mode = 'reply' | 'note'

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
  const canReply = can('reply')
  const canNote = can('add_note')
  const [body, setBody] = useState('')
  const [assetId, setAssetId] = useState<string | null>(null)
  const [draftPromptId, setDraftPromptId] = useState<string | null>(null)
  // Reply or internal note. A role that cannot reply but can note (corporate) starts — and
  // stays — in note mode; it is the only thing it is allowed to write here.
  const [mode, setMode] = useState<Mode>(canReply ? 'reply' : 'note')
  // Escape hides the palette without touching the draft; typing again reopens it.
  const [paletteDismissed, setPaletteDismissed] = useState(false)
  // The "Quick" button opens the same palette the '/' prefix opens, without rewriting a
  // draft the agent has already typed.
  const [paletteForced, setPaletteForced] = useState(false)
  const [woOpen, setWoOpen] = useState(false)
  const box = useRef<HTMLTextAreaElement>(null)
  const send = useSendMessage(conversationId)
  const addNote = useAddNote(conversationId)
  const { data: replies } = useQuickReplies()
  const render = useRenderQuickReply()
  const { setPresence } = useRealtime()

  // A draft handed down from the prompt banner (Task 15) loads once, then clears.
  // This must be an effect, not a render-phase setState — the latter loops.
  useEffect(() => {
    if (draftBody) {
      setBody(draftBody)
      setDraftPromptId(draftPromptIdIn ?? null)
      // A suggested guest reply is an SMS, never a note — switch back if we were noting.
      if (canReply) setMode('reply')
      box.current?.focus()
      onDraftConsumed?.()
    }
  }, [draftBody, draftPromptIdIn, onDraftConsumed, canReply])

  // The palette opens only when '/' starts the draft — 'either/or' must not trigger it.
  const slashOpen = body.startsWith('/') && !body.includes(' ') && !body.includes('\n')
  const paletteOpen = mode === 'reply' && !paletteDismissed && (slashOpen || paletteForced)
  const segments = segmentCount(body)
  const characters = charCount(body)
  const optedOut = conversation.guest.smsConsentStatus === 'opted_out'
  const noteMode = mode === 'note'
  const pending = noteMode ? addNote.isPending : send.isPending
  const error = noteMode ? addNote.error : send.error

  function submit() {
    const trimmed = body.trim()
    if (!trimmed || pending) return
    // Otherwise a palette forced open over a draft that was never typed into (a prompt
    // draft, an asset link) would still be open over the emptied box afterwards.
    setPaletteForced(false)
    if (noteMode) {
      addNote.mutate({ body: trimmed }, { onError: () => setBody(trimmed) })
      setBody('')
      // Both are outbound-SMS attribution and neither travelled with the note, so leaving
      // them armed would attach them to whatever is sent next instead.
      setAssetId(null)
      setDraftPromptId(null)
      return
    }
    // A quick reply still resolving (or one that failed) must never let the raw
    // /shortcut text reach a guest — block the send until it settles.
    if (render.isPending) return
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

  // A role with neither capability (none ship today, but the matrix is data) legitimately
  // reaches the thread and must get it read-only.
  if (!canReply && !canNote) return null

  return (
    <div className="border-t border-border p-3">
      {optedOut && !noteMode ? (
        <p className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          This guest has opted out of SMS. A send will be rejected unless they text START.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {error.message}
        </p>
      ) : null}

      {render.error ? (
        <p role="alert" className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {render.error.message}
        </p>
      ) : null}

      {canNote ? (
        <div className="mb-2 inline-flex gap-1 rounded border border-border3 bg-surface2 p-0.5">
          {canReply ? (
            <ModeTab label="Reply" active={!noteMode} onClick={() => setMode('reply')} />
          ) : null}
          <ModeTab
            label="Note"
            active={noteMode}
            onClick={() => {
              setMode('note')
              setPaletteForced(false)
            }}
            note
          />
        </div>
      ) : null}

      <div className="relative">
        {paletteOpen && replies ? (
          <QuickReplyPalette
            replies={replies}
            // A forced-open palette over an existing draft lists everything rather than
            // filtering by prose that was never a shortcut.
            term={slashOpen ? body : ''}
            onClose={() => {
              setPaletteDismissed(true)
              setPaletteForced(false)
            }}
            onPick={(reply) => {
              setPaletteForced(false)
              // The server interpolates; we never substitute tokens client-side.
              render.mutate(
                { id: reply.id, conversationId },
                {
                  onSuccess: (rendered) => {
                    setBody(rendered.body)
                    box.current?.focus()
                  },
                  onError: () => {
                    // Never leave the raw /shortcut sitting in the box — a client that
                    // did would risk sending it to the guest as literal text.
                    setBody('')
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
          placeholder={
            noteMode ? 'Internal note — not sent to the guest' : 'Type a reply, or / for a quick reply'
          }
          // `cn` concatenates, it does not resolve Tailwind conflicts, and the palette's
          // own source order otherwise lets Textarea's bg-surface2/text-text win here.
          // focus:!border-accent must be important too: Textarea's only focus affordance is
          // that border (it sets focus:outline-none), and a plain one loses to !border-noteBorder.
          className={
            noteMode
              ? '!border-noteBorder focus:!border-accent !bg-noteBg !text-noteText'
              : undefined
          }
          onChange={(event) => {
            setBody(event.target.value)
            setPaletteDismissed(false)
            // A forced-open palette has no term, so it never narrows as you type and its
            // document-level Enter handler would swallow a newline and overwrite the draft
            // with a template. Typing releases it; the '/' path re-opens on its own terms.
            setPaletteForced(false)
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
        {/* A note is not an SMS: no quick replies, no asset link, no segment cost. */}
        {!noteMode ? (
          <>
            <Button
              onClick={() => {
                setPaletteDismissed(false)
                setPaletteForced(true)
                box.current?.focus()
              }}
            >
              Quick
            </Button>
            <AssetPicker
              onPick={(asset) => {
                setAssetId(asset.id)
                setBody((current) => `${current}${current ? ' ' : ''}${window.location.origin}/a/${asset.shortCode}`)
              }}
            />
            {can('create_work_order') ? (
              <Button onClick={() => setWoOpen(true)}>
                Work order
              </Button>
            ) : null}
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
          </>
        ) : null}
        <Button
          variant="primary"
          className="ml-auto"
          loading={pending}
          onClick={submit}
          title="Ctrl+Enter"
        >
          {noteMode ? 'Add note' : 'Send'}
        </Button>
      </div>

      {/* Mounted only while open: the modal needs a ToastProvider, and an always-mounted
          copy would impose that on every consumer of the composer for nothing. */}
      {woOpen ? (
        <CreateWorkOrderModal
          conversationId={conversationId}
          open
          onClose={() => setWoOpen(false)}
        />
      ) : null}
    </div>
  )
}

function ModeTab({
  label,
  active,
  onClick,
  note,
}: {
  label: string
  active: boolean
  onClick: () => void
  note?: boolean
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded px-3 py-1 text-xs font-bold uppercase tracking-wide',
        active
          ? note
            ? 'bg-noteBg text-noteText'
            : 'bg-surface text-text'
          : 'text-text3 hover:text-text',
      )}
    >
      {label}
    </button>
  )
}
