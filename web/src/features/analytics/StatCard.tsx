// StatCard.tsx
export function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-card border border-border2 bg-surface p-4">
      <p className="text-[13px] font-bold uppercase tracking-wider text-text3">{label}</p>
      <p className="font-mono text-3xl font-bold leading-none tracking-tight">{value}</p>
      {sub ? <p className="text-[12.5px] text-text3">{sub}</p> : null}
    </div>
  )
}
