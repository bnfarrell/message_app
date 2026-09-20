import { useState } from 'react'
import { useLogFeed } from '../../api/hooks/log'
import { useDepartments } from '../../api/hooks/users'
import type { LogEntryOut } from '../../api/types'
import { EmptyState, Spinner } from '../../components/ui'
import { dayKey } from '../../lib/time'
import { LogComposer } from './LogComposer'
import { LogEntryCard } from './LogEntryCard'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'
const HEADING = 'text-xs font-bold uppercase tracking-widest text-text3'

const SHIFTS = [
  { value: 'am', label: 'AM' },
  { value: 'pm', label: 'PM' },
  { value: 'overnight', label: 'Overnight' },
]

/** Consecutive runs of the viewer's local day (spec §7 departure — see time.ts's dayKey).
 *  Entries arrive newest-first from the server and are never re-sorted here, so a run
 *  only breaks where the day actually changes. */
function groupByDay(entries: LogEntryOut[]): { key: string; entries: LogEntryOut[] }[] {
  const groups: { key: string; entries: LogEntryOut[] }[] = []
  for (const entry of entries) {
    const key = dayKey(entry.createdAt)
    const current = groups[groups.length - 1]
    if (current?.key === key) {
      current.entries.push(entry)
    } else {
      groups.push({ key, entries: [entry] })
    }
  }
  return groups
}

function dayHeading(key: string): string {
  if (key === dayKey(new Date().toISOString())) return 'Today'
  const [year, month, day] = key.split('-').map(Number)
  return new Date(year!, month! - 1, day!).toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

export function LogPage() {
  const [shift, setShift] = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [mentioningMe, setMentioningMe] = useState(false)
  const { data: departments } = useDepartments()
  const { data, isPending, error } = useLogFeed({
    shift: shift || undefined,
    departmentId: departmentId || undefined,
    mentioningMe,
  })

  const pinned = data?.pinned ?? []
  const groups = groupByDay(data?.entries ?? [])

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Log</h1>
      </header>

      <LogComposer />

      <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
        <div>
          <label className={HEADING} htmlFor="log-filter-shift">Shift</label>
          <select
            id="log-filter-shift"
            className={SELECT}
            value={shift}
            onChange={(event) => setShift(event.target.value)}
          >
            <option value="">All shifts</option>
            {SHIFTS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={HEADING} htmlFor="log-filter-department">Department</label>
          <select
            id="log-filter-department"
            className={SELECT}
            value={departmentId}
            onChange={(event) => setDepartmentId(event.target.value)}
          >
            <option value="">All departments</option>
            {(departments ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>

        <label className="flex h-9 items-center gap-2 text-xs font-semibold text-text3">
          <input
            type="checkbox"
            checked={mentioningMe}
            onChange={(event) => setMentioningMe(event.target.checked)}
          />
          Mentioning me
        </label>
      </div>

      <div role="tablist" className="flex gap-1.5 border-b border-border px-4">
        <button
          type="button"
          role="tab"
          aria-selected={true}
          className="inline-flex h-11 items-center px-3.5 text-[13.5px] font-semibold text-text md:h-9"
        >
          Posts
        </button>
      </div>

      {isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : error ? (
        <EmptyState title="Could not load the log" hint={error.message} />
      ) : pinned.length === 0 && groups.length === 0 ? (
        <EmptyState title="No log entries yet" hint="Posts will show up here once someone adds one." />
      ) : (
        <div className="flex flex-col gap-4 p-4">
          {pinned.length > 0 ? (
            <section className="flex flex-col gap-2">
              <h2 className={HEADING}>Pinned</h2>
              {pinned.map((entry) => (
                <LogEntryCard key={entry.id} entry={entry} />
              ))}
            </section>
          ) : null}

          {groups.map((group) => (
            <section key={group.key} className="flex flex-col gap-2">
              <h2 className={HEADING}>
                {dayHeading(group.key)} · {group.entries.length} post{group.entries.length === 1 ? '' : 's'}
              </h2>
              {group.entries.map((entry) => (
                <LogEntryCard key={entry.id} entry={entry} />
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
