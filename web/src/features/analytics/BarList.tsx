// BarList.tsx — horizontal bars with direct labels (the mockup's .hbar)
import { cn } from '../../lib/cn'

export function BarList({
  rows,
}: {
  rows: { label: string; value: string; share: number; danger?: boolean }[]
}) {
  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((row) => (
        <li key={row.label} className="flex items-center gap-3">
          <span className="w-16 flex-none text-xs text-text3">{row.label}</span>
          <span className="flex h-2.5 flex-1 overflow-hidden rounded-r bg-surface2">
            <span
              className={cn('h-2.5 rounded-r', row.danger ? 'bg-danger' : 'bg-accent')}
              style={{ width: `${Math.min(100, row.share * 100)}%` }}
            />
          </span>
          <span
            className={cn('w-12 flex-none text-right font-mono text-xs', row.danger && 'text-dangerText')}
          >
            {row.value}
          </span>
        </li>
      ))}
    </ul>
  )
}
