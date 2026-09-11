import { useState } from 'react'
import { usePatchConversation } from '../../api/hooks/conversations'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { ConversationDetail } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, Dropdown } from '../../components/ui'
import { ArchiveDialog } from './ArchiveDialog'
import { CreateWorkOrderModal } from './CreateWorkOrderModal'

function snoozePresets(now: Date): { label: string; at: Date }[] {
  const hour = (n: number) => new Date(now.getTime() + n * 3600_000)
  const tomorrow9 = new Date(now)
  tomorrow9.setDate(tomorrow9.getDate() + 1)
  tomorrow9.setHours(9, 0, 0, 0)
  return [
    { label: '1 hour', at: hour(1) },
    { label: '4 hours', at: hour(4) },
    { label: 'Tomorrow 9 am', at: tomorrow9 },
  ]
}

const ITEM = 'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface2'

export function ConversationActions({ conversation }: { conversation: ConversationDetail }) {
  const { can } = useSession()
  const patch = usePatchConversation(conversation.id)
  const { data: staff } = useStaff()
  const { data: departments } = useDepartments()
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [woOpen, setWoOpen] = useState(false)
  // Captured once, not recomputed on every Dropdown re-render, so "1 hour" means an hour
  // from when this view opened, not from whenever the menu happens to redraw.
  const [now] = useState(() => new Date())

  return (
    <div className="flex items-center gap-2">
      {can('assign') ? (
        <Dropdown label="Assign" align="right">
          {(close) => (
            <>
              {(staff ?? []).map((person) => (
                <button
                  key={person.id}
                  role="menuitem"
                  className={ITEM}
                  onClick={() => {
                    close()
                    patch.mutate({ assignedUserId: person.id })
                  }}
                >
                  {person.firstName} {person.lastName}
                </button>
              ))}
              <hr className="my-1 border-border" />
              {(departments ?? []).map((department) => (
                <button
                  key={department.id}
                  role="menuitem"
                  className={ITEM}
                  onClick={() => {
                    close()
                    patch.mutate({ assignedDepartmentId: department.id })
                  }}
                >
                  {department.name}
                </button>
              ))}
              <hr className="my-1 border-border" />
              <button
                role="menuitem"
                className={ITEM}
                onClick={() => {
                  close()
                  // The server needs the explicit flag; a null would read as "no change".
                  patch.mutate({ clearAssignment: true })
                }}
              >
                Unassign
              </button>
            </>
          )}
        </Dropdown>
      ) : null}

      {can('assign') ? (
        <Dropdown label="Snooze" align="right">
          {(close) => (
            <>
              {snoozePresets(now).map((preset) => (
                <button
                  key={preset.label}
                  role="menuitem"
                  className={ITEM}
                  onClick={() => {
                    close()
                    patch.mutate({ snoozedUntil: preset.at.toISOString() })
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </>
          )}
        </Dropdown>
      ) : null}

      {can('create_work_order') ? (
        <Button onClick={() => setWoOpen(true)}>Create work order</Button>
      ) : null}

      {can('archive') ? <Button onClick={() => setArchiveOpen(true)}>Archive</Button> : null}

      <ArchiveDialog
        conversationId={conversation.id}
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
      />
      <CreateWorkOrderModal
        conversationId={conversation.id}
        open={woOpen}
        onClose={() => setWoOpen(false)}
      />
    </div>
  )
}
