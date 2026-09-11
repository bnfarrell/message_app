import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useGuest } from '../../api/hooks/users'
import type { ConversationDetail, StayOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Badge } from '../../components/ui'
import { ordinal } from '../../lib/ordinal'

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

/** `YYYY-MM-DD` only — parsed by hand so a date-only string is not shifted by the local zone. */
function ymd(date: string): [number, number, number] {
  const [y, m, d] = date.split('-').map(Number)
  return [y ?? 0, m ?? 1, d ?? 1]
}

/**
 * "JUN 2026 · 2N · CHECKED OUT". The mockup's line also carries a conversation count and a
 * star rating; `StayOut` has neither field, so neither is rendered.
 */
function stayLine(stay: StayOut): string {
  const [ay, am, ad] = ymd(stay.arrivalDate)
  const [dy, dm, dd] = ymd(stay.departureDate)
  const nights = Math.max(
    0,
    Math.round((Date.UTC(dy, dm - 1, dd) - Date.UTC(ay, am - 1, ad)) / 86_400_000),
  )
  return [
    `${MONTHS[am - 1] ?? '—'} ${ay}`,
    `${nights}N`,
    stay.status.replace('_', ' ').toUpperCase(),
  ].join(' · ')
}

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
  const { can } = useSession()
  const name = [guest.firstName, guest.lastName].filter(Boolean).join(' ') || guest.phoneE164
  const consent = CONSENT[guest.smsConsentStatus] ?? CONSENT['unknown']!
  const pending = draftPrompts.filter((p) => p.status === 'pending')
  // GET /guests/<id> is gated on `view_all_conversations` server-side, which dept_staff
  // lacks — asking for it as dept_staff would only earn a 403.
  const canSeeHistory = can('view_all_conversations')
  const guestDetail = useGuest(canSeeHistory ? guest.id : undefined)
  const previousStays = (guestDetail.data?.stays ?? []).filter((s) => s.id !== stay?.id)

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

      {canSeeHistory ? (
        <Section title="Previous stays">
          {/* The only fallible section in this panel: everything else renders from props.
              A failed lookup must not read as "first-time guest" — the two are opposites. */}
          {guestDetail.error ? (
            <p className="text-xs text-dangerText">Stay history unavailable</p>
          ) : guestDetail.isPending ? null : previousStays.length === 0 ? (
            <p className="text-xs text-text3">None</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {previousStays.map((s) => (
                <li key={s.id} className="font-mono text-xs text-text2">
                  {stayLine(s)}
                </li>
              ))}
            </ul>
          )}
        </Section>
      ) : null}
    </aside>
  )
}
