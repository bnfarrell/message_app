import { useAckLogEntry } from '../../api/hooks/log'
import type { LogEntryOut } from '../../api/types'
import { Button } from '../../components/ui'

export function AckBar({ entry }: { entry: LogEntryOut }): JSX.Element | null {
  const ack = useAckLogEntry()
  if (!entry.requiresAck) return null

  const ackedCount = entry.acks?.length ?? 0
  const outstanding = entry.outstanding ?? []

  return (
    <div className="flex flex-col gap-1 border-t border-border2 pt-2">
      <div className="flex items-center gap-2">
        <progress
          value={ackedCount}
          max={entry.ackExpectedCount}
          className="h-1.5 w-24 accent-accent"
        />
        <span className="text-xs text-text3">
          {ackedCount} of {entry.ackExpectedCount} acknowledged
        </span>
        {entry.ackedByMe ? (
          <span className="ml-auto text-xs font-semibold text-text">You acknowledged this</span>
        ) : entry.canAck ? (
          <Button
            variant="primary"
            className="ml-auto h-7 px-2 text-xs"
            loading={ack.isPending}
            onClick={() => ack.mutate(entry.id)}
          >
            Acknowledge
          </Button>
        ) : null}
      </div>
      {outstanding.length > 0 ? (
        <p className="text-xs text-text3">Outstanding: {outstanding.map((p) => p.name).join(', ')}</p>
      ) : null}
    </div>
  )
}
