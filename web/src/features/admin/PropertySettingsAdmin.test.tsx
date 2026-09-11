import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import type { PropertySettingsOut } from '../../api/types'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { PropertySettingsAdmin } from './PropertySettingsAdmin'

const SETTINGS: PropertySettingsOut = {
  id: 'prop-a',
  name: 'Harbourview Hotel',
  code: 'HVH',
  timezone: 'America/New_York',
  address: '1 Harbour Way',
  phone: '+15550100',
  smsNumber: '+15550111',
  brand: 'Harbourview Collection',
  currency: 'USD',
  logoUrl: 'https://example.test/logo.png',
  primaryColor: '#0F62FE',
  slaMinutes: 15,
  autoResolveHours: 4,
  helpText: 'Reply STOP to opt out. Call the front desk on 555 0100.',
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Fields the real server cannot store a null in: the NOT NULL columns on `Property`
// (name, timezone, currency) plus `_BAG_REQUIRED` in server/app/domain/properties.py
// (slaMinutes, autoResolveHours). `patch_changes` answers 400 `required` for every one of
// them, so a mock that echoed a null back would put the form in a state production
// cannot reach — which is exactly how a `value={null}` React warning got into this file
// once without a single test going red (ruling D96).
const NON_NULLABLE = ['name', 'timezone', 'currency', 'slaMinutes', 'autoResolveHours'] as const

function failed(message: string, details: Record<string, string>): Response {
  return json({ error: { code: 'VALIDATION_FAILED', message, details } }, 400)
}

/** guests.normalize_phone: E.164 out, or a refusal. MIN_SENDER_DIGITS is 2. */
function e164(raw: string): string | null {
  const trimmed = raw.trim()
  const digits = trimmed.replace(/\D/g, '')
  if (trimmed.startsWith('+')) return digits.length >= 2 ? `+${digits}` : null
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`
  return null
}

/**
 * Models PATCH /properties/<id>/settings rather than echoing the patch back: it refuses what
 * server/app/domain/_patch.py refuses and normalises what server/app/domain/properties.py
 * normalises (currency upper-cased, phone and smsNumber to E.164, timezone checked against the
 * zone database). The screen's own hint copy promises the admin that normalisation, so an
 * echoing mock would let a test assert a lie and still pass.
 */
function patchSettings(sent: Record<string, unknown>): Response {
  const cleared = NON_NULLABLE.filter((f) => f in sent && sent[f] === null)
  if (cleared.length > 0) {
    return failed(
      `Cannot be cleared: ${cleared.join(', ')}`,
      Object.fromEntries(cleared.map((f) => [f, 'required'])),
    )
  }

  const stored = { ...sent }
  for (const field of ['phone', 'smsNumber'] as const) {
    const value = stored[field]
    if (typeof value !== 'string') continue
    const normalised = e164(value)
    if (normalised === null) return failed('Invalid phone number', { [field]: 'invalid_phone_number' })
    stored[field] = normalised
  }
  if (typeof stored.timezone === 'string') {
    try {
      new Intl.DateTimeFormat('en-US', { timeZone: stored.timezone })
    } catch {
      return failed('Invalid time zone', { timezone: 'invalid_timezone' })
    }
  }
  if (typeof stored.currency === 'string') stored.currency = stored.currency.toUpperCase()
  return json({ ...SETTINGS, ...stored })
}

function serve(override?: (url: string, init?: RequestInit) => Response | null) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const claimed = override?.(String(input), init)
    if (claimed) return Promise.resolve(claimed)
    if (init?.method === 'PATCH') {
      // The server answers with the full normalised record, not an echo of the patch.
      return Promise.resolve(patchSettings(JSON.parse(String(init.body)) as Record<string, unknown>))
    }
    return Promise.resolve(json(SETTINGS))
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <PropertySettingsAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/property' },
  )
}

const patched = () => vi.mocked(fetch).mock.calls.filter(([, i]) => i?.method === 'PATCH')

describe('PropertySettingsAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads every editable field', async () => {
    mount()
    expect(await screen.findByLabelText('Property name')).toHaveValue('Harbourview Hotel')
    expect(screen.getByLabelText('Time zone')).toHaveValue('America/New_York')
    expect(screen.getByLabelText('Address')).toHaveValue('1 Harbour Way')
    expect(screen.getByLabelText('Phone')).toHaveValue('+15550100')
    expect(screen.getByLabelText('SMS number')).toHaveValue('+15550111')
    expect(screen.getByLabelText('Brand')).toHaveValue('Harbourview Collection')
    expect(screen.getByLabelText('Currency')).toHaveValue('USD')
    expect(screen.getByLabelText('Logo URL')).toHaveValue('https://example.test/logo.png')
    expect(screen.getByLabelText('Brand colour')).toHaveValue('#0F62FE')
    expect(screen.getByLabelText('Overdue after (minutes)')).toHaveValue(15)
    expect(screen.getByLabelText('Auto-resolve after (hours)')).toHaveValue(4)
    expect(screen.getByLabelText(/HELP reply/)).toHaveValue(SETTINGS.helpText!)
  })

  it('shows `code` as read-only context, with no input to send it back', async () => {
    mount()
    // PropertySettingsPatch has no `code` and CamelModel forbids extras, so an input for it would
    // turn every save into a 400.
    expect(await screen.findByText('HVH')).toBeInTheDocument()
    expect(screen.queryByLabelText(/property code/i)).not.toBeInTheDocument()
  })

  it('saves the form and re-reads the server’s normalised answer, not what was typed', async () => {
    const user = userEvent.setup()
    mount()
    const phone = await screen.findByLabelText('Phone')
    await user.clear(phone)
    await user.type(phone, '(555) 012-3456')
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ ...SETTINGS, phone: '+15550123456', currency: 'USD' })
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(JSON.parse(String(patched()[0]![1]!.body))).toMatchObject({ phone: '(555) 012-3456' })
    // normalize_phone stores E.164; showing the typed string back would misreport what is saved,
    // and inbound SMS routing matches on the stored form.
    await waitFor(() => expect(screen.getByLabelText('Phone')).toHaveValue('+15550123456'))
    expect(await screen.findByRole('status')).toHaveTextContent('Saved.')
  })

  it('shows the currency the server stored, upper-cased, not the case that was typed', async () => {
    const user = userEvent.setup()
    mount()
    const currency = await screen.findByLabelText('Currency')
    await user.clear(currency)
    await user.type(currency, 'eur')
    // No override: properties.py does `v.upper()` before storing, so a form that redisplayed
    // the typed string would misreport the stored value.
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(JSON.parse(String(patched()[0]![1]!.body))).toMatchObject({ currency: 'eur' })
    await waitFor(() => expect(screen.getByLabelText('Currency')).toHaveValue('EUR'))
  })

  it('shows the SMS number in the E.164 form the server routes on, not as typed', async () => {
    const user = userEvent.setup()
    mount()
    const sms = await screen.findByLabelText('SMS number')
    await user.clear(sms)
    await user.type(sms, '(555) 011-2222')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // channels/inbound.py routes an inbound SMS by matching the stored E.164 form, so what
    // the box shows after a save has to be what routing will match on.
    await waitFor(() => expect(screen.getByLabelText('SMS number')).toHaveValue('+15550112222'))
  })

  it('clears a nullable field to null rather than to an empty string', async () => {
    const user = userEvent.setup()
    mount()
    await user.clear(await screen.findByLabelText('Address'))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(JSON.parse(String(patched()[0]![1]!.body)).address).toBeNull()
  })

  it('clears a REQUIRED box to null too, so the admin reads copy rather than a raw regex', async () => {
    const user = userEvent.setup()
    mount()
    await user.clear(await screen.findByLabelText('Currency'))
    // No per-test override: the default handler refuses a cleared required field the way
    // patch_changes does (D96), so this asserts against a server the real one could be.
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // `""` fails in Pydantic and the admin reads "String should match pattern ^[A-Za-z]{3}$".
    // `null` reaches patch_changes instead, which answers `required` — a code the shared map
    // already words. The server half of this is pinned by
    // server/tests/test_property_settings.py::test_patch_settings_rejects_an_explicit_null_on_a_required_field,
    // which asserts {"currency": null} -> 400 details {"currency": "required"} for real.
    expect(JSON.parse(String(patched()[0]![1]!.body)).currency).toBeNull()
    const message = await screen.findByText('This field is required.')
    expect(message.parentElement).toContainElement(screen.getByLabelText('Currency'))
  })

  it('clears an emptied name to null as well, not to an empty string', async () => {
    const user = userEvent.setup()
    mount()
    await user.clear(await screen.findByLabelText('Property name'))
    // The real server refuses this (`name` is NOT NULL) and never echoes a null name back, and
    // the default handler now refuses it too — a 200 here would make the form render
    // `value={null}` in a state production cannot reach, which is how two React warnings got
    // into this file with a green suite (D96).
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(JSON.parse(String(patched()[0]![1]!.body)).name).toBeNull()
    const message = await screen.findByText('This field is required.')
    expect(message.parentElement).toContainElement(screen.getByLabelText('Property name'))
  })

  it('offers the stored zone as a real option even when the browser list omits it', async () => {
    const original = Intl.supportedValuesOf
    // A browser with no supportedValuesOf falls back to a short list, and this zone is
    // deliberately not on it. Without the stored value being forced in, the select would render
    // showing its first option while the server still held Antarctica/Troll — and the next save
    // would quietly move the property to a different time zone nobody asked for.
    Object.defineProperty(Intl, 'supportedValuesOf', { value: undefined, configurable: true })
    serve((_url, init) =>
      init?.method ? null : json({ ...SETTINGS, timezone: 'Antarctica/Troll' }),
    )
    try {
      mount()
      const select = await screen.findByLabelText('Time zone')
      expect(select).toHaveValue('Antarctica/Troll')
      expect(screen.getByRole('option', { name: 'Antarctica/Troll' })).toBeInTheDocument()
    } finally {
      Object.defineProperty(Intl, 'supportedValuesOf', { value: original, configurable: true })
    }
  })

  it('pins a bad time zone to the Time zone field, not to a bare banner', async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByLabelText('Time zone')
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Invalid time zone',
                          details: { timezone: 'invalid_timezone' } } }, 400)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // The domain validator raises a reason code; the shared normaliser words it (D93).
    const message = await screen.findByText('Not a recognised IANA time zone.')
    expect(message.parentElement).toContainElement(screen.getByLabelText('Time zone'))
    expect(screen.queryByText('invalid_timezone')).not.toBeInTheDocument()
  })

  it('pins a junk SMS number to its own box, in words', async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByLabelText('SMS number')
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Invalid phone number',
                          details: { smsNumber: 'invalid_phone_number' } } }, 400)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const message = await screen.findByText(/Enter a valid phone number/)
    expect(message.parentElement).toContainElement(screen.getByLabelText('SMS number'))
  })

  it('pins a slaMinutes of 0 to its own field, from the array shape of `details`', async () => {
    const user = userEvent.setup()
    mount()
    const sla = await screen.findByLabelText('Overdue after (minutes)')
    await user.clear(sla)
    await user.type(sla, '0')
    serve((_url, init) =>
      init?.method === 'PATCH'
        ? json({ error: { code: 'VALIDATION_FAILED', message: 'Invalid request body',
                          details: [{ loc: ['slaMinutes'], msg: 'Input should be greater than 0',
                                      type: 'greater_than' }] } }, 400)
        : null,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // Pydantic's array shape, not the object shape — a form written against only the object
    // shape would highlight nothing here, and 0 makes every conversation instantly overdue.
    const message = await screen.findByText('Input should be greater than 0')
    expect(message.parentElement).toContainElement(sla)
  })

  it('says the SLA change does not reach conversations that are already waiting', async () => {
    mount()
    await screen.findByLabelText('Overdue after (minutes)')
    // conv.sla_due_at is written once, when an inbound message arrives, and never recomputed.
    expect(screen.getByText(/Applies from the next inbound message/)).toBeInTheDocument()
  })

  it('says the HELP reply is read by guests', async () => {
    mount()
    expect(await screen.findByLabelText(/HELP reply/)).toBeInTheDocument()
    // The label alone could read as an internal note; the hint says who receives it.
    expect(screen.getByText(/Sent automatically, as an SMS, to any guest who texts HELP/))
      .toBeInTheDocument()
    expect(screen.getByText(/not an internal note/)).toBeInTheDocument()
  })

  it('renders primaryColor as a swatch of the stored value and nothing else', async () => {
    mount()
    await screen.findByLabelText('Brand colour')
    const swatch = screen.getByTestId('primary-color-swatch')
    expect(swatch).toHaveStyle({ background: '#0F62FE' })
    // It is a per-property brand colour, not part of this client's palette: it must not reach a
    // CSS custom property or the document theme.
    expect(document.documentElement.style.getPropertyValue('--accent')).toBe('')
    expect(document.documentElement.getAttribute('style') ?? '').not.toContain('#0F62FE')
  })

  it('reverts the form to the stored record', async () => {
    const user = userEvent.setup()
    mount()
    const name = await screen.findByLabelText('Property name')
    await user.clear(name)
    await user.type(name, 'Something else')
    await user.click(screen.getByRole('button', { name: 'Revert' }))
    expect(screen.getByLabelText('Property name')).toHaveValue('Harbourview Hotel')
    expect(patched()).toHaveLength(0)
  })
})
