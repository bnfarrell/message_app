import type { GuestThread } from '../../api/types'
import { formatClock } from '../../lib/time'

/**
 * Every colour inside the frame is hard-coded on purpose — it imitates iOS Messages, not
 * this product, so it must not follow the app theme. A guest's phone does not restyle
 * itself when the staff app toggles to dark; themed chrome around fixed iOS bubbles is
 * neither the mockup's phone nor a coherent dark theme, but a third thing that reads as a
 * rendering bug. docs/mockups/Simulator.dc.html paints the phone in these same fixed
 * colours for the same reason. The page AROUND the frame stays fully tokenised — this
 * component is the only hard-coded colour in the app, and /sim is dev-only.
 */
const RECEIVED = { background: '#e9e9eb', color: '#111111' }
const SENT = { background: '#34c759', color: '#ffffff' }
const PHONE = {
  bezel: '#000000',
  body: '#ffffff',
  header: '#f7f7f8',
  hairline: '#d1d1d6',
  secondary: '#8e8e93',
  text: '#111111',
}

export function PhoneFrame({ thread, smsNumber }: { thread: GuestThread; smsNumber: string | null }) {
  return (
    <div
      className="mx-auto flex h-full w-full max-w-[380px] flex-col overflow-hidden rounded-[28px] border"
      style={{ borderColor: PHONE.bezel, background: PHONE.body, color: PHONE.text }}
    >
      <header
        className="flex flex-col items-center gap-0.5 border-b px-4 py-3"
        style={{ borderColor: PHONE.hairline, background: PHONE.header }}
      >
        <span
          className="grid h-8 w-8 place-items-center rounded-md font-mono text-[11px] font-bold"
          style={{ background: PHONE.secondary, color: PHONE.body }}
        >
          HV
        </span>
        <p className="text-[13px] font-semibold">{thread.propertyName}</p>
        <p className="font-mono text-[11px]" style={{ color: PHONE.secondary }}>
          {smsNumber ?? thread.phone}
        </p>
      </header>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3" style={{ background: PHONE.body }}>
        {thread.messages.length === 0 ? (
          <p className="mt-6 text-center text-xs" style={{ color: PHONE.secondary }}>
            No messages yet.
          </p>
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
