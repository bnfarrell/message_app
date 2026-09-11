import { useEffect, useState } from 'react'
import type { QuickReplyOut } from '../../api/types'
import { cn } from '../../lib/cn'

/** §5.3: filter by shortcut and body. Shortcut-prefix matches rank first. */
export function filterQuickReplies(replies: QuickReplyOut[], term: string): QuickReplyOut[] {
  const active = replies.filter((r) => r.active)
  const needle = term.trim().toLowerCase().replace(/^\//, '')
  if (!needle) return active

  const byShortcut: QuickReplyOut[] = []
  const byText: QuickReplyOut[] = []
  for (const reply of active) {
    if (reply.shortcut.toLowerCase().replace(/^\//, '').startsWith(needle)) byShortcut.push(reply)
    else if (
      reply.title.toLowerCase().includes(needle) ||
      reply.body.toLowerCase().includes(needle)
    )
      byText.push(reply)
  }
  return [...byShortcut, ...byText]
}

export function QuickReplyPalette({
  replies,
  term,
  onPick,
  onClose,
}: {
  replies: QuickReplyOut[]
  term: string
  onPick: (reply: QuickReplyOut) => void
  onClose: () => void
}) {
  const matches = filterQuickReplies(replies, term)
  const [index, setIndex] = useState(0)

  // A new term means a new list; keep the cursor in range rather than off the end.
  useEffect(() => {
    setIndex(0)
  }, [term])

  useEffect(() => {
    // Nothing to navigate: leave the keyboard alone rather than silently eating arrow
    // keys and Escape while the palette has nothing visible to show for it.
    if (matches.length === 0) return

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setIndex((i) => Math.min(i + 1, matches.length - 1))
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        setIndex((i) => Math.max(i - 1, 0))
      } else if (event.key === 'Enter') {
        // Ctrl/Cmd+Enter is the composer's send. Picking as well would fire a render whose
        // result lands in the box the send just emptied, as a template nobody asked for.
        if (event.ctrlKey || event.metaKey) return
        const picked = matches[index]
        if (picked) {
          event.preventDefault()
          onPick(picked)
        }
      } else if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [matches, index, onPick, onClose])

  if (matches.length === 0) return null

  return (
    <ul
      role="listbox"
      className="absolute bottom-full left-0 right-0 mb-2 max-h-64 overflow-y-auto rounded-card border border-border2 bg-surface py-1"
    >
      {matches.map((reply, i) => (
        <li
          key={reply.id}
          data-testid={`qr-${reply.id}`}
          role="option"
          aria-selected={i === index}
          onMouseDown={(event) => {
            event.preventDefault() // keep focus in the textarea
            onPick(reply)
          }}
          className={cn(
            'cursor-pointer px-3 py-2',
            i === index ? 'bg-surface2' : 'hover:bg-surface2',
          )}
        >
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs font-semibold text-roomNum">{reply.shortcut}</span>
            <span className="text-[13px] font-semibold">{reply.title}</span>
          </div>
          <p className="truncate text-xs text-text3">{reply.body}</p>
        </li>
      ))}
    </ul>
  )
}
