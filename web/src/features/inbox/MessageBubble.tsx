import type { MessageOut } from '../../api/types'
import { Badge, Button } from '../../components/ui'
import { cn } from '../../lib/cn'
import { formatClock } from '../../lib/time'

const STATUS_COPY: Record<MessageOut['deliveryStatus'], string> = {
  queued: 'Sending…',
  sent: 'Sent',
  delivered: 'Delivered',
  failed: 'Failed',
  undelivered: 'Failed',
}

export function MessageBubble({
  message,
  authorName,
  onRetry,
}: {
  message: MessageOut
  authorName: string | null
  onRetry?: () => void
}) {
  const outbound = message.direction === 'outbound'
  const automated = message.authorType === 'system' || message.authorType === 'automation'
  const failed = message.deliveryStatus === 'failed' || message.deliveryStatus === 'undelivered'

  return (
    <div
      data-testid="bubble-row"
      className={cn('flex w-full', outbound && !automated ? 'justify-end' : 'justify-start')}
    >
      <div className="max-w-[470px]">
        <div
          data-testid="bubble"
          className={cn(
            'rounded-card px-3.5 py-3 text-[14.5px] leading-relaxed',
            automated
              ? 'border border-autoBorder bg-autoBg text-autoText'
              : outbound
                ? 'bg-outBg text-outText'
                : 'border border-border2 bg-surface2 text-text',
          )}
        >
          {message.body}
        </div>

        {message.redacted ? (
          <Badge tone="warn" className="mt-1.5">
            Card number redacted
          </Badge>
        ) : null}

        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-text3">
          {automated ? <span>Automatic</span> : null}
          {message.sentAt ? <span>{formatClock(message.sentAt)}</span> : null}
          {authorName && !automated ? <span>{authorName}</span> : null}
          {outbound ? (
            <span className={failed ? 'font-semibold text-dangerText' : undefined}>
              {STATUS_COPY[message.deliveryStatus]}
              {failed && message.providerErrorCode ? ` · ${message.providerErrorCode}` : ''}
            </span>
          ) : null}
          {failed && onRetry ? (
            <Button variant="ghost" className="h-7" onClick={onRetry}>
              Retry
            </Button>
          ) : null}
        </p>
      </div>
    </div>
  )
}
