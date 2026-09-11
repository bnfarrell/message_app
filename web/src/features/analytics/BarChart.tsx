import { cn } from '../../lib/cn'

export function BarChart<T extends { count: number }>({
  buckets,
  labelOf,
  highlightOf,
  height = 160,
}: {
  buckets: T[]
  labelOf: (bucket: T) => string
  highlightOf?: (bucket: T) => boolean
  height?: number
}) {
  // An all-zero series must not divide by zero; a max of 1 keeps every bar at 0%.
  const max = Math.max(1, ...buckets.map((b) => b.count))

  return (
    <div className="relative" style={{ height }}>
      {[0.25, 0.5, 0.75].map((fraction) => (
        <div
          key={fraction}
          aria-hidden="true"
          className="absolute left-0 right-0 h-px bg-border"
          style={{ bottom: `${fraction * 100}%` }}
        />
      ))}
      <div className="flex h-full items-end gap-[3px]">
        {buckets.map((bucket, index) => (
          <div key={index} className="flex h-full flex-1 items-end" title={labelOf(bucket)}>
            <div
              data-testid="bar"
              className={cn(
                'w-full rounded-t',
                highlightOf?.(bucket) ? 'bg-danger' : 'bg-accent',
              )}
              style={{ height: `${(bucket.count / max) * 100}%` }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
