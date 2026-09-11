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
