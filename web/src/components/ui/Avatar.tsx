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
