import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSession } from '../auth/SessionContext'
import { landingPath } from '../auth/capabilities'
import { useTheme } from '../theme/ThemeContext'
import { cn } from '../lib/cn'
import { ADMIN_SECTIONS, visibleNavGroups } from './navModel'
import { NavIcon } from './NavIcon'

type Entry = { id: string; label: string; group: string; run: () => void }

function isTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

/**
 * Ruling D63: this is a NAVIGATION palette, not a record search, and it makes no server call.
 * The only `q=` parameter on the whole server is quick_replies.py:16 — there is no
 * conversation, guest or work-order search endpoint, and inbox search was disclosed to the
 * user as unbuildable in Phase 1 for exactly that reason.
 */
export function CommandPalette() {
  const { can, memberships, setPropertyId, logout } = useSession()
  const { resolved, setTheme } = useTheme()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState('')
  const [index, setIndex] = useState(0)
  const trigger = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const listId = useId()

  const close = useCallback(() => {
    setOpen(false)
    trigger.current?.focus()
  }, [])

  const entries = useMemo<Entry[]>(() => {
    const out: Entry[] = []
    // Exactly the rail's own filter: a palette that offers a destination the user cannot
    // reach, or lists admin sections to a non-admin, is the defect to avoid here.
    for (const group of visibleNavGroups(can)) {
      for (const item of group.items) {
        out.push({
          id: `go-${item.to}`,
          label: item.label,
          group: 'Go to',
          run: () => navigate(item.to),
        })
      }
    }
    if (can('manage_admin')) {
      for (const section of ADMIN_SECTIONS) {
        out.push({
          id: `admin-${section.to}`,
          label: section.label,
          group: 'Admin',
          run: () => navigate(section.to),
        })
      }
    }
    if (memberships.length > 1) {
      for (const m of memberships) {
        out.push({
          id: `property-${m.propertyId}`,
          label: `Switch to ${m.propertyName}`,
          group: 'Property',
          run: () => {
            setPropertyId(m.propertyId)
            // The new property's role may differ; land where it belongs.
            navigate(landingPath(m.role), { replace: true })
          },
        })
      }
    }
    out.push({
      id: 'theme',
      label: `Switch to ${resolved === 'dark' ? 'light' : 'dark'} theme`,
      group: 'Session',
      run: () => setTheme(resolved === 'dark' ? 'light' : 'dark'),
    })
    out.push({ id: 'signout', label: 'Sign out', group: 'Session', run: () => logout() })
    return out
  }, [can, memberships, resolved, logout, navigate, setPropertyId, setTheme])

  const matches = useMemo(() => {
    const needle = term.trim().toLowerCase()
    if (!needle) return entries
    return entries.filter((e) => `${e.group} ${e.label}`.toLowerCase().includes(needle))
  }, [entries, term])

  const active = matches[Math.min(index, matches.length - 1)]

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'k' && event.key !== 'K') return
      if (!event.ctrlKey && !event.metaKey) return
      // Ctrl+K belongs to the message composer and every other text box while it has focus.
      if (isTextEntry(event.target)) return
      event.preventDefault()
      setTerm('')
      setIndex(0)
      setOpen(true)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    if (open) input.current?.focus()
  }, [open])

  function onDialogKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close()
      return
    }
    // The input is the only focusable thing in here; options are addressed through
    // aria-activedescendant. Holding Tab inside keeps the dialog modal for the keyboard.
    if (event.key === 'Tab') {
      event.preventDefault()
      input.current?.focus()
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (matches.length === 0) return
      const step = event.key === 'ArrowDown' ? 1 : -1
      setIndex((i) => (Math.min(i, matches.length - 1) + step + matches.length) % matches.length)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      if (!active) return
      close()
      active.run()
    }
  }

  let lastGroup = ''

  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-label="Jump to a screen (Ctrl K)"
        aria-keyshortcuts="Control+K Meta+K"
        onClick={() => {
          setTerm('')
          setIndex(0)
          setOpen(true)
        }}
        className="inline-flex h-8 items-center gap-2 rounded-md border border-border3 bg-bg2 px-2.5 text-xs font-semibold text-text3 hover:text-text"
      >
        <NavIcon name="search" className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Jump to</span>
        <kbd className="rounded border border-border2 px-1.5 font-mono text-[10px] text-text3">
          Ctrl K
        </kbd>
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[12vh]"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close()
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            onKeyDown={onDialogKeyDown}
            className="w-full max-w-[440px] overflow-hidden rounded-card border border-border2 bg-surface"
          >
            <input
              ref={input}
              type="text"
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={active ? `${listId}-${active.id}` : undefined}
              aria-label="Jump to a screen or action"
              placeholder="Jump to a screen or action"
              value={term}
              onChange={(event) => {
                setTerm(event.target.value)
                setIndex(0)
              }}
              className="h-12 w-full border-b border-border bg-surface px-4 text-sm text-text placeholder:text-text4 focus:outline-none"
            />
            {/* `listitem` is not an allowed child of `listbox`, and nor is a bare paragraph:
                some screen readers then mis-count or skip the options. role="presentation"
                on the wrappers makes the option divs the listbox's own children. */}
            <ul id={listId} role="listbox" aria-label="Results" className="max-h-72 overflow-y-auto py-1">
              {matches.length === 0 ? (
                <li role="presentation" className="px-4 py-3 text-sm text-text3">
                  Nothing matches that.
                </li>
              ) : null}
              {matches.map((entry, i) => {
                const heading = entry.group === lastGroup ? null : entry.group
                lastGroup = entry.group
                return (
                  <li role="presentation" key={entry.id}>
                    {heading ? (
                      <p
                        role="presentation"
                        className="px-4 pb-1 pt-2 text-[10px] font-bold uppercase tracking-[0.12em] text-text4"
                      >
                        {heading}
                      </p>
                    ) : null}
                    <div
                      id={`${listId}-${entry.id}`}
                      role="option"
                      aria-selected={entry === active}
                      onMouseDown={(event) => {
                        event.preventDefault()
                        close()
                        entry.run()
                      }}
                      onMouseEnter={() => setIndex(i)}
                      className={cn(
                        'flex h-10 cursor-pointer items-center px-4 text-sm font-semibold text-text',
                        entry === active ? 'bg-sel' : null,
                      )}
                    >
                      {entry.label}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        </div>
      ) : null}
    </>
  )
}
