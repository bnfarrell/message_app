import { useStaffDirectory } from '../../api/hooks/staffMessages'
import { Avatar, EmptyState, Spinner } from '../../components/ui'
import { matchesName } from './matchesName'

const ROLE_LABEL: Record<string, string> = {
  agent: 'Front Desk User',
  dept_staff: 'Staff',
  supervisor: 'Supervisor',
  manager: 'Manager',
  admin: 'Admin',
  corporate: 'Corporate',
}

export function NewConversationList({
  excludeUserIds,
  onStart,
  filter = '',
}: {
  excludeUserIds: string[]
  onStart: (userId: string) => void
  filter?: string
}) {
  const { data, isPending, error } = useStaffDirectory()

  if (isPending) {
    return (
      <div className="grid place-items-center p-6">
        <Spinner />
      </div>
    )
  }
  if (error) return <EmptyState title="Could not load staff" hint={error.message} />

  const exclude = new Set(excludeUserIds)
  const rows = (data ?? []).filter(
    (entry) =>
      !exclude.has(entry.userId) && matchesName(`${entry.firstName} ${entry.lastName}`, filter),
  )
  // With nothing typed, an empty directory (everyone already has a DM) simply isn't shown; with
  // a filter active, an empty result must say so rather than the section silently vanishing.
  if (rows.length === 0) return filter.trim() ? <EmptyState title="No staff match" /> : null

  return (
    <ul className="flex flex-col">
      {rows.map((entry) => (
        <li key={entry.userId}>
          <button
            type="button"
            onClick={() => onStart(entry.userId)}
            title={`Click to start messaging ${entry.firstName} ${entry.lastName}`}
            className="flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left hover:bg-surface2"
          >
            <Avatar name={`${entry.firstName} ${entry.lastName}`} tone="muted" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">
                {entry.firstName} {entry.lastName}
              </span>
              <span className="block truncate text-[12px] text-text3">
                {entry.departmentName ?? ROLE_LABEL[entry.role] ?? entry.role}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
