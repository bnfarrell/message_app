import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '../../lib/cn'

export function Dropdown({
  label,
  children,
  align = 'left',
}: {
  label: ReactNode
  children: (close: () => void) => ReactNode
  align?: 'left' | 'right'
}) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  function close() {
    setOpen(false)
    trigger.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    function onDocumentClick(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('mousedown', onDocumentClick)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocumentClick)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={root} className="relative">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-11 items-center gap-2 rounded border border-border3 bg-surface px-4 text-sm font-semibold text-text"
      >
        {label}
      </button>
      {open ? (
        <div
          role="menu"
          className={cn(
            'absolute z-40 mt-1 min-w-[200px] overflow-hidden rounded border border-border2 bg-surface py-1',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          {children(close)}
        </div>
      ) : null}
    </div>
  )
}
