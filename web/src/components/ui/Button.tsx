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
