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
