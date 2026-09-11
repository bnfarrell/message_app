### Task 4: UI primitives

**Files:**
- Create: `web/src/components/ui/Button.tsx`, `Input.tsx`, `Textarea.tsx`, `Badge.tsx`, `Avatar.tsx`, `Spinner.tsx`, `EmptyState.tsx`, `Dialog.tsx`, `Dropdown.tsx`, `Toast.tsx`
- Create: `web/src/components/ui/index.ts`
- Test: `web/src/components/ui/Button.test.tsx`, `web/src/components/ui/Dialog.test.tsx`, `web/src/components/ui/Dropdown.test.tsx`, `web/src/components/ui/Avatar.test.tsx`

**Interfaces:**
- Consumes: `cn` (Task 1).
- Produces, all re-exported from `components/ui/index.ts`:
  - `Button(props: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'primary' | 'ghost' | 'danger'; loading?: boolean })`
  - `Input(props: InputHTMLAttributes<HTMLInputElement>)`, `Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>)`
  - `Badge(props: { tone?: 'neutral' | 'ok' | 'warn' | 'danger' | 'presence' | 'note'; children: ReactNode; className?: string })`
  - `Avatar(props: { name: string; tone?: 'accent' | 'muted' | 'presence'; size?: 22 | 26 | 32; title?: string })`
  - `Spinner(props: { className?: string })`
  - `EmptyState(props: { title: string; hint?: string; action?: ReactNode })`
  - `Dialog(props: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean })`
  - `Dropdown(props: { label: ReactNode; children: (close: () => void) => ReactNode; align?: 'left' | 'right' })`
  - `ToastProvider`, `useToast(): (message: string, tone?: 'ok' | 'danger') => void`

**Shape language from §5.0, applied here once so no feature re-derives it:** 44 px controls, 8 px radii (10 px on cards), 1 px borders, **no shadows**, amber `accent` for primary actions only.

`Avatar` renders initials, not images — `UserOut.avatarUrl` is `null` for every seeded user, and the mockups show initial tiles throughout.

- [ ] **Step 1: Write the failing tests**

`web/src/components/ui/Button.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'

describe('Button', () => {
  it('is 44px tall and uses the surface treatment by default', () => {
    render(<Button>Assign</Button>)
    expect(screen.getByRole('button', { name: 'Assign' }).className).toContain('h-11')
  })

  it('uses the amber accent only for the primary variant', () => {
    const { rerender } = render(<Button variant="primary">Send</Button>)
    expect(screen.getByRole('button').className).toContain('bg-accent')
    rerender(<Button>Send</Button>)
    expect(screen.getByRole('button').className).not.toContain('bg-accent')
  })

  it('blocks clicks and marks itself busy while loading', async () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Send
      </Button>,
    )
    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('still respects an explicit disabled prop', () => {
    render(<Button disabled>Send</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
```

`web/src/components/ui/Dialog.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Dialog } from './Dialog'

function open(onClose = vi.fn()) {
  render(
    <Dialog open onClose={onClose} title="Create work order">
      <input aria-label="Title" />
      <button>Save</button>
    </Dialog>,
  )
  return onClose
}

describe('Dialog', () => {
  it('renders nothing when closed', () => {
    render(
      <Dialog open={false} onClose={vi.fn()} title="Create work order">
        body
      </Dialog>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('is a labelled modal dialog when open', () => {
    open()
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Create work order')
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
  })

  it('moves focus into the dialog so keyboard users are not left on the page behind', async () => {
    open()
    await vi.waitFor(() =>
      expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true),
    )
  })

  it('closes on Escape', async () => {
    const onClose = open()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('closes on a backdrop click but not on a click inside the panel', async () => {
    const onClose = open()
    await userEvent.click(screen.getByTestId('dialog-backdrop'))
    expect(onClose).toHaveBeenCalledOnce()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
```

`web/src/components/ui/Dropdown.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Dropdown } from './Dropdown'

function setup() {
  render(
    <Dropdown label="Assign">
      {(close) => (
        <button role="menuitem" onClick={close}>
          Ava
        </button>
      )}
    </Dropdown>,
  )
}

describe('Dropdown', () => {
  it('starts closed and reports its state to assistive tech', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Assign' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('opens on click and renders its items in a menu', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Ava' })).toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the trigger', async () => {
    setup()
    const trigger = screen.getByRole('button', { name: 'Assign' })
    await userEvent.click(trigger)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('closes when an item calls the close callback it is handed', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await userEvent.click(screen.getByRole('menuitem', { name: 'Ava' }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('closes on an outside click', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await userEvent.click(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
```

`web/src/components/ui/Avatar.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Avatar } from './Avatar'

describe('Avatar', () => {
  it('shows two initials for a full name', () => {
    render(<Avatar name="Sarah Chen" />)
    expect(screen.getByText('SC')).toBeInTheDocument()
  })

  it('shows one initial for a single name', () => {
    render(<Avatar name="Ava" />)
    expect(screen.getByText('A')).toBeInTheDocument()
  })

  it('falls back to ? for an empty name rather than rendering blank', () => {
    render(<Avatar name="   " />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('exposes the full name to assistive tech', () => {
    render(<Avatar name="Marcus Reyes" />)
    expect(screen.getByTitle('Marcus Reyes')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd web && npx vitest run src/components/ui
```

Expected: FAIL — none of the four modules resolve.

- [ ] **Step 3: Write the simple primitives**

`web/src/components/ui/Spinner.tsx`:

```tsx
import { cn } from '../../lib/cn'

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      data-testid="spinner"
      className={cn(
        'inline-block h-5 w-5 animate-spin rounded-full border-2 border-border3 border-t-accent',
        className,
      )}
    />
  )
}
```

`web/src/components/ui/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'
import { Spinner } from './Spinner'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'ghost' | 'danger'
  loading?: boolean
}

const VARIANTS = {
  default: 'border border-border3 bg-surface text-text hover:bg-surface2',
  primary: 'border border-accent bg-accent text-accentText hover:opacity-90',
  ghost: 'border-none bg-transparent px-2.5 text-text3 hover:text-text',
  danger: 'border border-danger bg-dangerBg text-dangerText hover:opacity-90',
} as const

export function Button({ variant = 'default', loading, className, children, ...rest }: Props) {
  return (
    <button
      {...rest}
      // A loading button must not fire twice; disabled covers both pointer and keyboard.
      disabled={rest.disabled || loading}
      aria-busy={loading ? 'true' : undefined}
      className={cn(
        'inline-flex h-11 items-center gap-2 rounded px-4 text-sm font-semibold',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        className,
      )}
    >
      {loading ? <Spinner className="h-4 w-4" /> : null}
      {children}
    </button>
  )
}
```

`web/src/components/ui/Input.tsx`:

```tsx
import type { InputHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={cn(
        'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text',
        'placeholder:text-text4 focus:border-accent focus:outline-none',
        className,
      )}
    />
  )
}
```

`web/src/components/ui/Textarea.tsx`:

```tsx
import type { TextareaHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={cn(
        'w-full rounded border border-border3 bg-surface2 p-3 text-sm leading-relaxed text-text',
        'placeholder:text-text4 focus:border-accent focus:outline-none',
        className,
      )}
    />
  )
}
```

`web/src/components/ui/Badge.tsx` — the mockups' `.tag`:

```tsx
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

const TONES = {
  neutral: 'bg-tagBg text-tagText',
  ok: 'bg-okBg text-okText',
  warn: 'bg-warnBg text-warnText',
  danger: 'bg-dangerBg text-dangerText',
  presence: 'bg-presenceBg text-presenceText',
  note: 'bg-noteBg text-noteText',
} as const

export function Badge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: keyof typeof TONES
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-md px-2 text-xs font-semibold tracking-wide',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
```

`web/src/components/ui/Avatar.tsx` — the mockups' `.av`:

```tsx
import { cn } from '../../lib/cn'

const TONES = {
  accent: 'bg-accent',
  muted: 'bg-avMuted',
  presence: 'bg-presenceAv',
} as const

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0]![0]!.toUpperCase()
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase()
}

export function Avatar({
  name,
  tone = 'muted',
  size = 26,
  title,
}: {
  name: string
  tone?: keyof typeof TONES
  size?: 22 | 26 | 32
  title?: string
}) {
  return (
    <span
      title={title ?? name}
      style={{ width: size, height: size }}
      className={cn(
        'inline-flex flex-none items-center justify-center rounded-md text-[11px] font-bold',
        'text-avText',
        TONES[tone],
      )}
    >
      {initialsOf(name)}
    </span>
  )
}
```

`web/src/components/ui/EmptyState.tsx`:

```tsx
import type { ReactNode } from 'react'

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-10 text-center">
      <p className="text-sm font-semibold text-text2">{title}</p>
      {hint ? <p className="max-w-xs text-xs text-text3">{hint}</p> : null}
      {action}
    </div>
  )
}
```

- [ ] **Step 4: Write `Dialog.tsx`**

Focus moves in on open and back to the previously focused element on close, so keyboard users are never stranded behind a modal.

```tsx
import { useEffect, useRef, type ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { Button } from './Button'

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const panel = useRef<HTMLDivElement>(null)
  const restoreTo = useRef<Element | null>(null)

  useEffect(() => {
    if (!open) return
    restoreTo.current = document.activeElement
    const focusable = panel.current?.querySelector<HTMLElement>(
      'input, textarea, select, button, [href], [tabindex]:not([tabindex="-1"])',
    )
    ;(focusable ?? panel.current)?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      ;(restoreTo.current as HTMLElement | null)?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div
        data-testid="dialog-backdrop"
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          'relative w-full rounded-card border border-border2 bg-surface',
          wide ? 'max-w-2xl' : 'max-w-md',
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-bold uppercase tracking-widest text-text3">{title}</h2>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </div>
        <div className="flex flex-col gap-3 p-4">{children}</div>
        {footer ? (
          <div className="flex justify-end gap-2 border-t border-border px-4 py-3">{footer}</div>
        ) : null}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Write `Dropdown.tsx`**

```tsx
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
```

- [ ] **Step 6: Write `Toast.tsx`**

One live region, so a send failure or a saved change is announced rather than only coloured.

```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { cn } from '../../lib/cn'

type Toast = { id: number; message: string; tone: 'ok' | 'danger' }

const ToastContext = createContext<((message: string, tone?: 'ok' | 'danger') => void) | null>(null)

export function useToast() {
  const push = useContext(ToastContext)
  if (!push) throw new Error('useToast must be used inside a ToastProvider')
  return push
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback((message: string, tone: 'ok' | 'danger' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, message, tone }])
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 5000)
  }, [])

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'rounded border px-4 py-3 text-sm font-semibold',
              t.tone === 'ok'
                ? 'border-okBorder bg-okBg text-okText'
                : 'border-danger bg-dangerBg text-dangerText',
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
```

- [ ] **Step 7: Write `index.ts`**

```ts
export { Avatar, initialsOf } from './Avatar'
export { Badge } from './Badge'
export { Button } from './Button'
export { Dialog } from './Dialog'
export { Dropdown } from './Dropdown'
export { EmptyState } from './EmptyState'
export { Input } from './Input'
export { Spinner } from './Spinner'
export { Textarea } from './Textarea'
export { ToastProvider, useToast } from './Toast'
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 18 primitive tests plus Tasks 1-3's.

- [ ] **Step 9: Commit**

```bash
git add web/src/components/ui
git commit -m "feat(web): UI primitives in the mockups' shape language"
```

---

