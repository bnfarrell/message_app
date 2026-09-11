import { useEffect, useState, type ReactNode } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { usePatchPropertySettings, usePropertySettings } from '../../api/hooks/properties'
import type { PropertySettingsOut, PropertySettingsPatch } from '../../api/types'
import { Button, EmptyState, Input, Spinner, Textarea } from '../../components/ui'

// A form, not a table. Spec line 417 asks the non-quick-reply admin screens to "reuse the table +
// edit-panel pattern", but this endpoint edits a single record: there is no list to select from,
// so AdminTable has nothing to draw and EditPanel's 340px aside would be a side panel with no
// main content beside it. What is reused is the part that carries the pattern's look — EditPanel's
// LABEL/SELECT field styling, its banner, and the Input / Textarea / Button primitives — laid out
// as one settings form in the main column instead.

// Same strings EditPanel's fields use; kept in step by eye, as the other four screens already do.
const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'
const HINT = 'mt-1 text-xs text-text3'

/**
 * Enough zones to keep the control usable where `Intl.supportedValuesOf` is missing, without
 * pretending to be the IANA database. The server validates against real `zoneinfo`, so a zone
 * absent from this list is still storable — it just cannot be picked from a browser this old.
 */
const FALLBACK_ZONES = [
  'UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Toronto', 'Europe/London', 'Europe/Dublin', 'Europe/Lisbon', 'Europe/Paris',
  'Europe/Berlin', 'Europe/Madrid', 'Europe/Rome', 'Asia/Dubai', 'Asia/Singapore',
  'Asia/Tokyo', 'Australia/Sydney',
]

/**
 * `timezone` is validated server-side against IANA zones and a typo is a 422 the admin cannot act
 * on, so it is a picker rather than a text box.
 *
 * The stored value is always included even when the list does not carry it. Without that, a zone
 * this browser has never heard of would leave the select showing its *first* option while the
 * server still held the real one — and the next save would silently move the property to a
 * different time zone nobody asked for.
 */
function timezoneOptions(current: string): string[] {
  let zones: string[] = []
  try {
    zones = Intl.supportedValuesOf?.('timeZone') ?? []
  } catch {
    zones = []
  }
  if (zones.length === 0) zones = FALLBACK_ZONES
  return zones.includes(current) ? zones : [current, ...zones]
}

type Draft = {
  name: string
  timezone: string
  address: string
  phone: string
  smsNumber: string
  brand: string
  currency: string
  logoUrl: string
  primaryColor: string
  // Held as strings so the boxes stay controlled while they are empty; converted on save.
  slaMinutes: string
  autoResolveHours: string
  helpText: string
}

function draftFrom(s: PropertySettingsOut): Draft {
  return {
    name: s.name,
    timezone: s.timezone,
    address: s.address ?? '',
    phone: s.phone ?? '',
    smsNumber: s.smsNumber ?? '',
    brand: s.brand ?? '',
    currency: s.currency,
    logoUrl: s.logoUrl ?? '',
    primaryColor: s.primaryColor ?? '',
    slaMinutes: String(s.slaMinutes),
    autoResolveHours: String(s.autoResolveHours),
    helpText: s.helpText ?? '',
  }
}

/** An emptied nullable box clears the column; `""` would store an empty string instead of null. */
const orNull = (value: string) => (value.trim() === '' ? null : value)
/** An emptied required number sends null, which the server answers with "required" per field. */
const orNullNumber = (value: string) => (value.trim() === '' ? null : Number(value))

function patchFrom(draft: Draft): PropertySettingsPatch {
  return {
    name: draft.name,
    timezone: draft.timezone,
    currency: draft.currency,
    address: orNull(draft.address),
    phone: orNull(draft.phone),
    smsNumber: orNull(draft.smsNumber),
    brand: orNull(draft.brand),
    logoUrl: orNull(draft.logoUrl),
    primaryColor: orNull(draft.primaryColor),
    slaMinutes: orNullNumber(draft.slaMinutes),
    autoResolveHours: orNullNumber(draft.autoResolveHours),
    helpText: orNull(draft.helpText),
  }
}

export function PropertySettingsAdmin() {
  const { data, isPending, error } = usePropertySettings()
  const patch = usePatchPropertySettings()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saved, setSaved] = useState(false)

  // The PATCH response is the normalised record, so this also re-seeds the form after a save with
  // what was actually stored rather than with what was typed.
  useEffect(() => {
    if (data) setDraft(draftFrom(data))
  }, [data])

  const fields = fieldErrors(patch.error)
  const failure = patch.error?.message ?? null

  if (isPending) return <Shell><Spinner /></Shell>
  if (error) return <Shell><EmptyState title="Could not load settings" hint={error.message} /></Shell>
  if (!data || !draft) return <Shell><Spinner /></Shell>

  const set = (change: Partial<Draft>) => {
    setSaved(false)
    setDraft({ ...draft, ...change })
  }

  function save() {
    if (!draft) return
    patch.mutate(patchFrom(draft), { onSuccess: () => setSaved(true) })
  }

  return (
    <Shell>
      <form
        className="flex max-w-2xl flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault()
          save()
        }}
      >
        {failure ? (
          <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
            {failure}
          </p>
        ) : null}
        {saved && !failure ? (
          <p role="status" className="rounded border border-okBorder bg-okBg px-3 py-2 text-xs text-okText">
            Saved.
          </p>
        ) : null}

        <div>
          <label className={LABEL} htmlFor="prop-name">Property name</label>
          <Input id="prop-name" value={draft.name} maxLength={200}
                 onChange={(e) => set({ name: e.target.value })} />
          <FieldError message={fields.name} />
        </div>

        <div>
          <span className={LABEL}>Property code</span>
          {/* Returned by GET but absent from the Patch model: the code is unique across the whole
              install and identifies the property, so renaming it is not a settings edit. Sending
              it at all is a 400 (extra="forbid"), which is why it is not an input. */}
          <p className="font-mono text-sm text-text2">{data.code}</p>
          <p className={HINT}>Identifies this property across the install. Not editable here.</p>
        </div>

        <div>
          <label className={LABEL} htmlFor="prop-timezone">Time zone</label>
          <select id="prop-timezone" className={SELECT} value={draft.timezone}
                  onChange={(e) => set({ timezone: e.target.value })}>
            {timezoneOptions(data.timezone).map((zone) => (
              <option key={zone} value={zone}>{zone}</option>
            ))}
          </select>
          <FieldError message={fields.timezone} />
        </div>

        <div>
          <label className={LABEL} htmlFor="prop-address">Address</label>
          <Input id="prop-address" value={draft.address} maxLength={400}
                 onChange={(e) => set({ address: e.target.value })} />
          <FieldError message={fields.address} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL} htmlFor="prop-phone">Phone</label>
            <Input id="prop-phone" value={draft.phone} maxLength={32}
                   onChange={(e) => set({ phone: e.target.value })} />
            <FieldError message={fields.phone} />
          </div>
          <div>
            <label className={LABEL} htmlFor="prop-sms">SMS number</label>
            <Input id="prop-sms" value={draft.smsNumber} maxLength={32}
                   onChange={(e) => set({ smsNumber: e.target.value })} />
            <FieldError message={fields.smsNumber} />
            {/* Inbound routing matches Property.sms_number against the normalised To number, so
                this is the line guests text, not a display number. */}
            <p className={HINT}>
              Guests text this number. Saved in E.164 form, so it may come back reformatted.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL} htmlFor="prop-brand">Brand</label>
            <Input id="prop-brand" value={draft.brand} maxLength={100}
                   onChange={(e) => set({ brand: e.target.value })} />
            <FieldError message={fields.brand} />
          </div>
          <div>
            <label className={LABEL} htmlFor="prop-currency">Currency</label>
            <Input id="prop-currency" value={draft.currency} maxLength={3}
                   onChange={(e) => set({ currency: e.target.value })} />
            <FieldError message={fields.currency} />
            <p className={HINT}>Three letters, e.g. USD. Stored upper-cased.</p>
          </div>
        </div>

        <div>
          <label className={LABEL} htmlFor="prop-logo">Logo URL</label>
          <Input id="prop-logo" value={draft.logoUrl} maxLength={500}
                 onChange={(e) => set({ logoUrl: e.target.value })} />
          <FieldError message={fields.logoUrl} />
        </div>

        <div>
          <label className={LABEL} htmlFor="prop-color">Brand colour</label>
          <div className="flex items-center gap-2">
            <Input id="prop-color" className="font-mono" value={draft.primaryColor} maxLength={16}
                   onChange={(e) => set({ primaryColor: e.target.value })} />
            {/* The one inline colour in this wave, and it is not a palette colour: the value is
                supplied by the server and rendered as data so the admin can see what they stored.
                It is deliberately NOT wired into a CSS custom property — this property's brand
                colour has nothing to do with the client's own theme. */}
            <span
              aria-hidden="true"
              data-testid="primary-color-swatch"
              className="h-11 w-11 flex-none rounded border border-border3"
              style={{ background: draft.primaryColor || 'transparent' }}
            />
          </div>
          <FieldError message={fields.primaryColor} />
          <p className={HINT}>This property&rsquo;s own brand colour. It does not change this app&rsquo;s appearance.</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL} htmlFor="prop-sla">Overdue after (minutes)</label>
            {/* No `min`: a native `min` makes the browser refuse the submit and answer with its
                own tooltip, so the server's `gt=0` message — the one that explains that 0 would
                make every conversation instantly overdue — could never reach the field. The
                server is the single authority on validity here, as it is on every other box. */}
            <Input id="prop-sla" type="number" value={draft.slaMinutes}
                   onChange={(e) => set({ slaMinutes: e.target.value })} />
            <FieldError message={fields.slaMinutes} />
            {/* conv.sla_due_at is written when an inbound message arrives (domain/messages.py),
                never recomputed, so a change here cannot reach conversations that already have
                one. Saying so here is cheaper than the bug report. */}
            <p className={HINT}>
              Applies from the next inbound message. Conversations already waiting keep the
              deadline they were given.
            </p>
          </div>
          <div>
            <label className={LABEL} htmlFor="prop-autoresolve">Auto-resolve after (hours)</label>
            <Input id="prop-autoresolve" type="number" value={draft.autoResolveHours}
                   onChange={(e) => set({ autoResolveHours: e.target.value })} />
            <FieldError message={fields.autoResolveHours} />
          </div>
        </div>

        <div>
          <label className={LABEL} htmlFor="prop-help">HELP reply &mdash; guests read this</label>
          <Textarea id="prop-help" rows={3} value={draft.helpText} maxLength={1600}
                    onChange={(e) => set({ helpText: e.target.value })} />
          <FieldError message={fields.helpText} />
          <p className={HINT}>
            Sent automatically, as an SMS, to any guest who texts HELP. This is outbound guest copy,
            not an internal note.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button type="submit" variant="primary" loading={patch.isPending}>Save</Button>
          <Button type="button" onClick={() => { patch.reset(); setSaved(false); setDraft(draftFrom(data)) }}>
            Revert
          </Button>
        </div>
      </form>
    </Shell>
  )
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Property settings</h1>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  )
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}
