import { useState } from 'react'
import { usePatchWorkOrder } from '../../api/hooks/workOrders'
import { Button, Textarea } from '../../components/ui'

/**
 * WorkOrder.dc.html:130-131. The only route to WorkOrderPatch.comment was TransitionButtons,
 * and only for the two statuses that demand a reason, so the server's standalone branch
 * (`elif p.comment: work_orders.comment(...)`) was unreachable from the client.
 *
 * No capability gate: that PATCH route carries @require_auth and @require_property and nothing
 * else — the capability checks on it are for closing statuses only — so anyone who can open the
 * work order can comment on it, and inventing a gate here would put the client out of step with
 * the server.
 */
export function CommentBox({ workOrderId }: { workOrderId: string }) {
  const patch = usePatchWorkOrder(workOrderId)
  const [comment, setComment] = useState('')
  const text = comment.trim()

  return (
    <section className="rounded-card border border-border2 bg-surface p-4">
      <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.1em] text-text3">Comment</h2>
      {patch.error ? (
        <p
          role="alert"
          className="mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText"
        >
          {patch.error.message}
        </p>
      ) : null}
      <Textarea
        aria-label="Comment"
        rows={3}
        placeholder="Add a note for the team…"
        value={comment}
        onChange={(event) => setComment(event.target.value)}
      />
      <div className="mt-2 flex justify-end">
        <Button
          variant="primary"
          disabled={text.length === 0}
          loading={patch.isPending}
          // The hook already invalidates the detail query, so the note lands in the Timeline.
          onClick={() => patch.mutate({ comment: text }, { onSuccess: () => setComment('') })}
        >
          Comment
        </Button>
      </div>
    </section>
  )
}
