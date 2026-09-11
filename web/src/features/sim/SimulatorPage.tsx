import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useSendInbound, useSimEvents, useSimGuests, useSimThread } from '../../api/hooks/sim'
import type { SimGuest } from '../../api/types'
import { Avatar, Badge, Button, Input, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { PhoneFrame } from './PhoneFrame'

const CONSENT_TONE = {
  opted_in: 'ok',
  opted_out: 'danger',
  unknown: 'neutral',
} as const

// §5.4's quick buttons. The card number is Luhn-valid so §6's redaction actually fires.
const QUICK = [
  { label: 'STOP', body: 'STOP' },
  { label: 'HELP', body: 'HELP' },
  { label: '"AC is broken"', body: "The AC in our room isn't working at all, it's really warm" },
  { label: 'card number', body: 'my card is 4242 4242 4242 4242' },
]

export default function SimulatorPage() {
  const guests = useSimGuests()
  const events = useSimEvents()
  const [selected, setSelected] = useState<SimGuest | null>(null)
  const [manualPhone, setManualPhone] = useState('')
  const [draft, setDraft] = useState('')
  const send = useSendInbound()

  const thread = useSimThread(selected?.propertyId, selected?.phone)

  function post(body: string) {
    if (!selected || !body.trim()) return
    send.mutate({
      from: selected.phone,
      to: selected.propertySmsNumber ?? '',
      body: body.trim(),
    })
    setDraft('')
  }

  return (
    <div className="flex h-full flex-col bg-bg text-text">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-accent font-mono text-xs font-bold text-accentText">
          HV
        </span>
        <h1 className="text-base font-bold">Phone simulator</h1>
        <Badge tone="warn">DEV ONLY</Badge>
        <p className="text-xs text-text3">
          SMS_ADAPTER=mock · posts Twilio-shaped webhooks to /api/hooks/sms/inbound
        </p>
        <Link to="/app/inbox" className="ml-auto text-sm font-semibold text-accent hover:underline">
          Open staff inbox
        </Link>
      </header>

      <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)_360px]">
        <section className="flex min-h-0 flex-col rounded-card border border-border2 bg-surface">
          <h2 className="border-b border-border px-3.5 py-3 text-xs font-bold uppercase tracking-[0.1em] text-text3">
            Be a guest
          </h2>
          <div className="border-b border-border p-3">
            <Input
              placeholder="+1 555 … or pick below"
              value={manualPhone}
              onChange={(event) => setManualPhone(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && manualPhone.trim() && guests.data?.[0]) {
                  // An unseeded number still needs a property to post to; use the first one.
                  const template = guests.data[0]!
                  setSelected({
                    ...template,
                    guestId: 'manual',
                    name: manualPhone.trim(),
                    phone: manualPhone.trim(),
                    roomNumber: null,
                    inHouse: false,
                    smsConsentStatus: 'unknown',
                    willFail: manualPhone.trim().endsWith('0000'),
                  })
                }
              }}
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {guests.isPending ? (
              <div className="grid place-items-center p-6">
                <Spinner />
              </div>
            ) : (
              (guests.data ?? []).map((guest) => (
                <button
                  key={guest.guestId}
                  onClick={() => setSelected(guest)}
                  className={cn(
                    'flex w-full items-center gap-2.5 border-b border-border px-3.5 py-3 text-left',
                    selected?.guestId === guest.guestId
                      ? 'bg-sel shadow-[inset_3px_0_0_var(--accent)]'
                      : 'hover:bg-surface2',
                  )}
                >
                  <Avatar name={guest.name} size={32} tone="muted" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{guest.name}</span>
                    <span className="block truncate font-mono text-xs text-text3">
                      {guest.phone}
                      {guest.roomNumber ? ` · ${guest.roomNumber}` : ''}
                      {guest.inHouse ? ' · in-house' : ''}
                    </span>
                  </span>
                  <Badge tone={guest.willFail ? 'warn' : CONSENT_TONE[guest.smsConsentStatus]}>
                    {guest.willFail ? 'FAILS' : guest.smsConsentStatus.replace('_', ' ').toUpperCase()}
                  </Badge>
                </button>
              ))
            )}
          </div>
          <p className="border-t border-border p-3 text-xs text-text3">
            Numbers ending in 0000 fail delivery on purpose (mock error 30007) so you can test the
            retry path.
          </p>
        </section>

        <section className="flex min-h-0 flex-col gap-3">
          <div className="min-h-0 flex-1">
            {thread.data ? (
              <PhoneFrame thread={thread.data} smsNumber={selected?.propertySmsNumber ?? null} />
            ) : (
              <div className="grid h-full place-items-center rounded-card border border-border2 bg-surface text-sm text-text3">
                Pick a guest to see their thread.
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            {QUICK.map((quick) => (
              <button
                key={quick.label}
                disabled={!selected}
                onClick={() => post(quick.body)}
                className="inline-flex h-9 items-center rounded-full border border-border3 bg-surface px-3 text-[12.5px] font-semibold text-text2 disabled:opacity-50"
              >
                {quick.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Input
              placeholder={`Text as ${selected?.name.split(' ')[0] ?? 'guest'}…`}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') post(draft)
              }}
            />
            <Button
              variant="primary"
              disabled={!selected}
              loading={send.isPending}
              onClick={() => post(draft)}
            >
              Send
            </Button>
          </div>
          {send.error ? (
            <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
              {send.error.message}
            </p>
          ) : null}
        </section>

        <section className="flex min-h-0 flex-col rounded-card border border-border2 bg-surface">
          <h2 className="border-b border-border px-3.5 py-3 text-xs font-bold uppercase tracking-[0.1em] text-text3">
            What the server did live
          </h2>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {(events.data ?? []).length === 0 ? (
              <p className="p-3.5 text-xs text-text3">Nothing yet. Send a message.</p>
            ) : (
              (events.data ?? []).map((event, index) => (
                <div
                  key={`${event.at}-${index}`}
                  className="grid grid-cols-[72px_minmax(0,1fr)] gap-2.5 border-b border-border px-3.5 py-2 text-[12.5px]"
                >
                  <span className="font-mono text-text3">
                    {new Date(event.at).toLocaleTimeString([], { hour12: false })}
                  </span>
                  <span className="min-w-0">
                    <span className="font-semibold">{event.type}</span>
                    <span className="block truncate text-text3">
                      {Object.entries(event.payload)
                        .slice(0, 3)
                        .map(([key, value]) => `${key}=${String(value)}`)
                        .join(' · ')}
                    </span>
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
