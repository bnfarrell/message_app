import type { GuestThread } from '../../api/types'
import { formatClock } from '../../lib/time'

/**
 * These two bubble colours are hard-coded on purpose — they imitate iOS Messages,
 * not this product, so they must not follow the app theme. They are the only
 * hard-coded colours on this page; everything else uses the 45 design tokens.
 */
const RECEIVED = { background: '#e9e9eb', color: '#111111' }
const SENT = { background: '#34c759', color: '#ffffff' }

export function PhoneFrame({ thread, smsNumber }: { thread: GuestThread; smsNumber: string | null }) {
  return (
    <div className="mx-auto flex h-full w-full max-w-[380px] flex-col overflow-hidden rounded-[28px] border border-border3 bg-surface">
      <header className="flex flex-col items-center gap-0.5 border-b border-border bg-surface2 px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-accent font-mono text-[11px] font-bold text-accentText">
          HV
        </span>
        <p className="text-[13px] font-semibold text-text">{thread.propertyName}</p>
        <p className="font-mono text-[11px] text-text3">{smsNumber ?? thread.phone}</p>
      </header>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto bg-surface p-3">
        {thread.messages.length === 0 ? (
          <p className="mt-6 text-center text-xs text-text3">No messages yet.</p>
        ) : (
          thread.messages.map((message) => {
            // We are the guest here: the hotel's outbound message is what we received.
            const received = message.direction === 'outbound'
            return (
              <div
                key={message.id}
                data-testid={received ? 'sms-in' : 'sms-out'}
                className={`max-w-[78%] px-3 py-2 text-sm leading-snug ${
                  received
                    ? 'self-start rounded-2xl rounded-bl-sm'
                    : 'self-end rounded-2xl rounded-br-sm'
                }`}
                style={received ? RECEIVED : SENT}
              >
                {message.body}
                <span className="mt-0.5 block text-[10.5px] opacity-70">
                  {message.sentAt ? formatClock(message.sentAt) : '…'}
                  {received ? ` · ${message.deliveryStatus}` : ''}
                </span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
