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
