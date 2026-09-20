import { useEffect, useRef, useState } from 'react'
import type { LogMentionableOut } from '../../api/types'
import { cn } from '../../lib/cn'

export type MentionRef = { type: 'user' | 'department'; id: string }

/** Matches what `tokenFor` writes. Task 12's renderer parses entry bodies with this.
 *  Carries the `g` flag: it's a shared instance, so calling `.test()`/`.exec()` on it
 *  directly leaves `lastIndex` set and can silently miss matches on a later call.
 *  Use `split()`/`matchAll()` (or a fresh copy) instead. */
export const TOKEN_RE = /@\[([^\]]+)\]\((user|department):([0-9a-f-]{36})\)/g

/** §6.1: the id is authoritative, the display name is presentation only. */
export function tokenFor(option: LogMentionableOut): string {
  return `@[${option.displayName}](${option.type}:${option.id})`
}

/** Find an unterminated `@query` fragment ending at the caret, if any. */
function activeQuery(value: string, caret: number): { start: number; term: string } | null {
  const upToCaret = value.slice(0, caret)
  const at = upToCaret.lastIndexOf('@')
  if (at === -1) return null
  const term = upToCaret.slice(at + 1)
  // A space (or anything non-word) ends the mention query.
  if (!/^\w*$/.test(term)) return null
  return { start: at, term }
}

export function MentionInput({
  value,
  mentions,
  options,
  onChange,
  placeholder,
  id,
}: {
  value: string
  mentions: MentionRef[]
  options: LogMentionableOut[]
  onChange: (value: string, mentions: MentionRef[]) => void
  placeholder?: string
  id?: string
}) {
  // The textarea's own displayed text is buffered locally rather than re-derived from
  // `value` on every render: a parent that doesn't feed a new `value` back through
  // `onChange` synchronously (or doesn't re-render at all) would otherwise see React
  // reset the DOM value to the stale prop on the very next keystroke's render. `value`
  // still wins on an external change (draft load, submit-clear) via the effect below.
  const [text, setText] = useState(value)
  const [query, setQuery] = useState<{ start: number; term: string } | null>(null)
  const [index, setIndex] = useState(0)
  const [pendingCaret, setPendingCaret] = useState<number | null>(null)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setText(value)
  }, [value])

  // A pick replaces a text range programmatically, which leaves the browser's own caret
  // wherever it was inside the now-stale `@query` fragment. Move it to just after the
  // inserted token so typing continues naturally instead of landing mid-token.
  useEffect(() => {
    if (pendingCaret === null || !ref.current) return
    ref.current.selectionStart = pendingCaret
    ref.current.selectionEnd = pendingCaret
    setPendingCaret(null)
  }, [pendingCaret, text])

  const matches = query
    ? options.filter((o) => o.displayName.toLowerCase().includes(query.term.toLowerCase()))
    : []

  function pick(option: LogMentionableOut) {
    if (!query) return
    const token = tokenFor(option)
    // Replace using the query's own recorded extent (the "@" plus its term), not the
    // live caret: the caret can move — ArrowLeft/Right, Home/End, a click — without
    // ever firing `onChange`, which is the only thing that recomputes `query`. Using
    // the live caret there would splice the token in against a stale end-of-range and
    // leave a stray tail of the query text behind it.
    const queryEnd = query.start + 1 + query.term.length
    const next = text.slice(0, query.start) + token + text.slice(queryEnd)
    const already = mentions.some((m) => m.type === option.type && m.id === option.id)
    const nextMentions = already ? mentions : [...mentions, { type: option.type, id: option.id }]
    setText(next)
    setPendingCaret(query.start + token.length)
    onChange(next, nextMentions)
    setQuery(null)
    setIndex(0)
  }

  function handleChange(next: string, caret: number) {
    setText(next)
    onChange(next, mentions)
    const found = activeQuery(next, caret)
    setQuery(found)
    setIndex(0)
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (matches.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setIndex((i) => Math.min(i + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setIndex((i) => Math.max(i - 1, 0))
    } else if (event.key === 'Enter') {
      const picked = matches[index]
      if (picked) {
        event.preventDefault()
        pick(picked)
      }
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setQuery(null)
    }
  }

  return (
    <div className="relative">
      <textarea
        ref={ref}
        id={id}
        role="textbox"
        placeholder={placeholder}
        value={text}
        onChange={(event) => handleChange(event.target.value, event.target.selectionStart)}
        onKeyDown={handleKeyDown}
        className="w-full resize-none rounded-card border border-border2 bg-surface p-3 text-[13px] focus:outline-none"
      />
      {matches.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-y-auto rounded-card border border-border2 bg-surface py-1"
        >
          {matches.map((option, i) => (
            <li
              key={`${option.type}:${option.id}`}
              role="option"
              aria-selected={i === index}
              onMouseDown={(event) => {
                event.preventDefault() // keep focus in the textarea
                pick(option)
              }}
              className={cn(
                'cursor-pointer px-3 py-2 text-[13px]',
                i === index ? 'bg-surface2' : 'hover:bg-surface2',
              )}
            >
              <span className="font-semibold">{option.displayName}</span>
              {option.subtitle && <span className="ml-2 text-xs text-text3">{option.subtitle}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
