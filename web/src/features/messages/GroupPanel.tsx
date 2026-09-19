import { useState } from 'react'
import {
  useAddStaffParticipants,
  useCreateStaffConversation,
  useRemoveStaffParticipant,
  useStaffDirectory,
  useUpdateStaffGroup,
} from '../../api/hooks/staffMessages'
import type { StaffConversationOut } from '../../api/types'
import { Avatar, Button, Dialog, EmptyState, Input, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'

export function GroupPanel({
  open,
  onClose,
  existing,
}: {
  open: boolean
  onClose: () => void
  existing?: StaffConversationOut
}) {
  const { data: directory, isPending: directoryPending, error: directoryError } =
    useStaffDirectory()
  const create = useCreateStaffConversation()
  const update = useUpdateStaffGroup(existing?.id ?? '')
  const add = useAddStaffParticipants(existing?.id ?? '')
  const remove = useRemoveStaffParticipant(existing?.id ?? '')

  const existingIds = new Set((existing?.participants ?? []).map((p) => p.userId))
  const [name, setName] = useState(existing?.name ?? '')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  function toggle(userId: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
  }

  function submit() {
    const trimmed = name.trim()
    if (existing) {
      const renamed = trimmed.length > 0 && trimmed !== existing.name
      const adding = selected.size > 0
      if (renamed) update.mutate({ name: trimmed }, { onSuccess: adding ? undefined : onClose })
      if (adding) {
        // Guarded by `adding` (selected.size > 0), so this is never actually empty.
        add.mutate({ userIds: [...selected] as [string, ...string[]] }, { onSuccess: onClose })
      }
      if (!renamed && !adding) onClose()
      return
    }
    create.mutate({ kind: 'group', name: trimmed, userIds: [...selected] }, { onSuccess: onClose })
  }

  const busy = create.isPending || update.isPending || add.isPending
  const trimmedName = name.trim()
  const canSubmit = existing ? trimmedName.length > 0 : trimmedName.length > 0 && selected.size > 0
  const mutationError = create.error ?? update.error ?? add.error ?? remove.error

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={existing ? 'Manage group' : 'Create group'}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!canSubmit} onClick={submit}>
            {existing ? 'Save' : 'Create'}
          </Button>
        </>
      }
    >
      {mutationError ? (
        <p
          role="alert"
          className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText"
        >
          {mutationError.message}
        </p>
      ) : null}

      <Input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Group Name"
      />

      {existing ? (
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-wide text-text3">
            Members ({existing.participants.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {existing.participants.map((p) => (
              <span
                key={p.userId}
                className="flex items-center gap-1 rounded-full border border-border3 px-2 py-0.5 text-xs"
              >
                {p.firstName} {p.lastName}
                <button
                  type="button"
                  onClick={() => remove.mutate({ userId: p.userId })}
                  aria-label={`Remove ${p.firstName} ${p.lastName}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <p className="mb-1 text-xs font-bold uppercase tracking-wide text-text3">
          Add staff ({directory?.length ?? 0})
        </p>
        {directoryPending ? (
          <div className="grid place-items-center p-4">
            <Spinner />
          </div>
        ) : directoryError ? (
          <EmptyState title="Could not load staff" hint={directoryError.message} />
        ) : (
          <ul className="max-h-64 overflow-y-auto">
            {(directory ?? [])
              .filter((entry) => !existingIds.has(entry.userId))
              .map((entry) => (
                <li key={entry.userId}>
                  <button
                    type="button"
                    onClick={() => toggle(entry.userId)}
                    aria-pressed={selected.has(entry.userId)}
                    className={cn(
                      'flex w-full items-center gap-2 px-2 py-2 text-left text-sm',
                      selected.has(entry.userId) ? 'bg-sel' : 'hover:bg-surface2',
                    )}
                  >
                    <Avatar name={`${entry.firstName} ${entry.lastName}`} size={22} tone="muted" />
                    {entry.firstName} {entry.lastName}
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>
    </Dialog>
  )
}
