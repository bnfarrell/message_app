import { useState } from 'react'
import { usePatchConversation } from '../../api/hooks/conversations'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { ConversationDetail } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, Dropdown } from '../../components/ui'
import { ArchiveDialog } from './ArchiveDialog'
import { CreateWorkOrderModal } from './CreateWorkOrderModal'

type SnoozePreset = { label: string; hours: number } | { label: string; tomorrow9am: true }

const SNOOZE_PRESETS: SnoozePreset[] = [
  { label: '1 hour', hours: 1 },
  { label: '4 hours', hours: 4 },
  { label: 'Tomorrow 9 am', tomorrow9am: true },
]

// Computed fresh at the moment of the click — a preset must mean "N hours from now",
// not "N hours from whenever this conversation happened to be opened". An agent can sit
// on a conversation for a shift; a snoozedUntil computed from mount time could already be
// in the past by the time they click, snapping the conversation straight back out of snooze.
function snoozeTarget(preset: SnoozePreset): Date {
  if ('tomorrow9am' in preset) {
    const at = new Date()
    at.setDate(at.getDate() + 1)
    at.setHours(9, 0, 0, 0)
    return at
  }
  return new Date(Date.now() + preset.hours * 3600_000)
}

const ITEM = 'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface2'

export function ConversationActions({ conversation }: { conversation: ConversationDetail }) {
  const { can } = useSession()
  const patch = usePatchConversation(conversation.id)
  const { data: staff } = useStaff()
  const { data: departments } = useDepartments()
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [woOpen, setWoOpen] = useState(false)

  return (
    <div className="flex flex-wrap items-center gap-2">
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
              {SNOOZE_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  role="menuitem"
                  className={ITEM}
                  onClick={() => {
                    close()
                    patch.mutate({ snoozedUntil: snoozeTarget(preset).toISOString() })
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
