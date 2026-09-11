import { Link } from 'react-router-dom'
import type { WorkOrderOut } from '../../api/types'
import { Avatar, Badge } from '../../components/ui'
import { relativeTime } from '../../lib/time'
import { PRIORITY_TONE } from './transitions'

export function WorkOrderCard({
  workOrder,
  assigneeName,
  departmentName,
}: {
  workOrder: WorkOrderOut
  assigneeName: string | null
  departmentName: string | null
}) {
  return (
    <Link
      to={`/app/work-orders/${workOrder.id}`}
      className="flex flex-col gap-2 rounded-card border border-border2 bg-surface px-3 pb-2.5 pt-3 hover:border-border3"
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-[13px] font-semibold text-roomNum">
          {workOrder.locationRef ?? '—'}
        </span>
        <Badge tone={PRIORITY_TONE[workOrder.priority]}>{workOrder.priority}</Badge>
        {assigneeName ? (
          <Avatar name={assigneeName} size={22} tone="muted" className="ml-auto" />
        ) : null}
      </div>
      <p className="text-sm font-semibold leading-snug">{workOrder.title}</p>
      <p className="flex items-center gap-2 text-xs text-text3">
        <span>{departmentName ?? 'Unassigned'}</span>
        <span className="font-mono">{relativeTime(workOrder.createdAt)}</span>
      </p>
    </Link>
  )
}
