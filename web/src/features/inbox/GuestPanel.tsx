import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { ConversationDetail } from '../../api/types'
import { Badge } from '../../components/ui'
import { ordinal } from '../../lib/ordinal'

const CONSENT: Record<string, { tone: 'ok' | 'danger' | 'neutral'; label: string }> = {
  opted_in: { tone: 'ok', label: 'Opted in' },
  opted_out: { tone: 'danger', label: 'Opted out' },
  unknown: { tone: 'neutral', label: 'Consent unknown' },
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-border px-4 py-4">
      <h3 className="mb-2 text-xs font-bold uppercase tracking-[0.1em] text-text3">{title}</h3>
      {children}
    </section>
  )
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="text-xs text-text3">{label}</span>
      <span className="text-right text-[13px] font-semibold">{value}</span>
    </div>
  )
}

export function GuestPanel({ conversation }: { conversation: ConversationDetail }) {
  const { guest, stay, workOrders, draftPrompts, notes } = conversation
  const name = [guest.firstName, guest.lastName].filter(Boolean).join(' ') || guest.phoneE164
  const consent = CONSENT[guest.smsConsentStatus] ?? CONSENT['unknown']!
  const pending = draftPrompts.filter((p) => p.status === 'pending')

  return (
    // §5.2: three columns only at ≥1024px. Below that the guest panel must be genuinely
    // absent, not zero-width — `hidden` (not a width collapse) keeps its border from
    // still occupying the two-column layout.
    <aside className="hidden w-[300px] flex-none overflow-y-auto border-l border-border bg-bg2 lg:block">
      <Section title="Guest">
        <p className="text-sm font-semibold">{name}</p>
        <p className="font-mono text-xs text-text3">{guest.phoneE164}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {guest.loyaltyTier ? <Badge>{guest.loyaltyTier.toUpperCase()}</Badge> : null}
          {guest.vip ? <Badge tone="warn">VIP</Badge> : null}
        </div>
      </Section>

      <Section title="Stay">
        {stay ? (
          <>
            <Field label="Room" value={[stay.roomNumber, stay.roomType].filter(Boolean).join(' · ')} />
            <Field label="Dates" value={`${stay.arrivalDate} → ${stay.departureDate}`} />
            <Field label="Party" value={`${stay.adults} adults · ${stay.children} children`} />
            <Field label="History" value={`${ordinal(stay.stayCount)} stay`} />
            <Field label="Status" value={stay.status.replace('_', ' ')} />
          </>
        ) : (
          <p className="text-xs text-text3">No stay on file</p>
        )}
      </Section>

      <Section title="Consent">
        <Badge tone={consent.tone}>{consent.label}</Badge>
      </Section>

      <Section title="Work orders">
        {workOrders.length === 0 ? (
          <p className="text-xs text-text3">None</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {workOrders.map((wo) => (
              <li key={wo.id}>
                <Link
                  to={`/app/work-orders/${wo.id}`}
                  className="flex items-center justify-between gap-2 text-[13px] font-semibold hover:text-accent"
                >
                  <span className="truncate">{wo.title}</span>
                  <Badge>{wo.status.replace('_', ' ')}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Prompts">
        <p className="text-xs text-text3">
          {pending.length === 0 ? 'None pending' : `${pending.length} pending prompt${pending.length > 1 ? 's' : ''}`}
        </p>
      </Section>

      <Section title="Notes">
        {notes.length === 0 ? (
          <p className="text-xs text-text3">None</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {notes.slice(-5).map((note) => (
              <li key={note.id} className="rounded border border-noteBorder bg-noteBg p-2 text-xs text-noteText">
                {note.body}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </aside>
  )
}
