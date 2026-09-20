import type { PmUnitKind } from '../../api/types'
import { cn } from '../../lib/cn'
import { KINDS, KIND_LABELS } from './labels'

export type KindTab = PmUnitKind | 'all'

export function KindTabs({
  value,
  onChange,
  allowAll,
}: {
  value: KindTab
  onChange: (kind: KindTab) => void
  allowAll?: boolean
}) {
  const options: KindTab[] = allowAll ? ['all', ...KINDS] : KINDS
  return (
    <div role="tablist" className="flex flex-wrap gap-1.5 border-b border-border px-4">
      {options.map((kind) => (
        <button
          key={kind}
          type="button"
          role="tab"
          aria-selected={value === kind}
          onClick={() => onChange(kind)}
          className={cn(
            'inline-flex h-11 items-center px-3.5 text-[13.5px] font-semibold md:h-9',
            value === kind ? 'border-b-2 border-accent text-text' : 'text-text3 hover:text-text',
          )}
        >
          {kind === 'all' ? 'All' : KIND_LABELS[kind]}
        </button>
      ))}
    </div>
  )
}
