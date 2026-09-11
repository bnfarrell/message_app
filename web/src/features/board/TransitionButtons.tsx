import { useState } from 'react'
import { usePatchWorkOrder } from '../../api/hooks/workOrders'
import type { WorkOrderDetail, WorkOrderStatus } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, Dialog, Textarea } from '../../components/ui'
import { CLOSING_STATUSES, STATUS_LABELS, allowedTransitions } from './transitions'

/** Blocking or cancelling without a reason is not worth recording. */
const NEEDS_REASON: WorkOrderStatus[] = ['blocked', 'cancelled']

export function TransitionButtons({ workOrder }: { workOrder: WorkOrderDetail }) {
  const { can } = useSession()
  const patch = usePatchWorkOrder(workOrder.id)
  const [asking, setAsking] = useState<WorkOrderStatus | null>(null)
  const [comment, setComment] = useState('')

  const options = allowedTransitions(workOrder.status).filter(
    (status) => !CLOSING_STATUSES.includes(status) || can('close_work_order'),
  )

  function go(status: WorkOrderStatus, withComment?: string) {
    patch.mutate(withComment ? { status, comment: withComment } : { status })
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {patch.error ? (
        <p role="alert" className="w-full rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {patch.error.message}
        </p>
      ) : null}

      {options.map((status) => (
        <Button
          key={status}
          variant={status === 'complete' ? 'primary' : status === 'cancelled' ? 'danger' : 'default'}
          loading={patch.isPending && asking === null}
          onClick={() => (NEEDS_REASON.includes(status) ? setAsking(status) : go(status))}
        >
          {STATUS_LABELS[status]}
        </Button>
      ))}

      <Dialog
        open={asking !== null}
        onClose={() => {
          setAsking(null)
          setComment('')
        }}
        title={asking === 'cancelled' ? 'Cancel work order' : 'Block work order'}
        footer={
          <>
            <Button
              onClick={() => {
                setAsking(null)
                setComment('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={patch.isPending}
              onClick={() => {
                if (!asking) return
                go(asking, comment.trim() || undefined)
                setAsking(null)
                setComment('')
              }}
            >
              Confirm
            </Button>
          </>
        }
      >
        <label className="text-xs font-bold uppercase tracking-widest text-text3" htmlFor="wo-reason">
          Why?
        </label>
        <Textarea
          id="wo-reason"
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      </Dialog>
    </div>
  )
}
