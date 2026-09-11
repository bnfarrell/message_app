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
