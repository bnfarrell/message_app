import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return (
      <textarea
        {...rest}
        ref={ref}
        className={cn(
          'w-full rounded border border-border3 bg-surface2 p-3 text-sm leading-relaxed text-text',
          'placeholder:text-text4 focus:border-accent focus:outline-none',
          className,
        )}
      />
    )
  },
)
