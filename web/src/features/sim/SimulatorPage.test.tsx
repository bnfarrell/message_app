import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../../test/harness'
import SimulatorPage from './SimulatorPage'

const GUESTS = [
  {
    propertyId: 'prop-a', propertyName: 'Harbourview Hotel', propertySmsNumber: '+15550100',
    guestId: 'g-1', name: 'Sarah Chen', phone: '+15551234567', roomNumber: '412',
    inHouse: true, stayId: 'stay-1', smsConsentStatus: 'opted_in', willFail: false,
  },
  {
    propertyId: 'prop-a', propertyName: 'Harbourview Hotel', propertySmsNumber: '+15550100',
    guestId: 'g-2', name: 'Tom Becker', phone: '+15552000000', roomNumber: '516',
    inHouse: true, stayId: 'stay-2', smsConsentStatus: 'opted_in', willFail: true,
  },
  {
    propertyId: 'prop-a', propertyName: 'Harbourview Hotel', propertySmsNumber: '+15550100',
    guestId: 'g-3', name: 'Lena Park', phone: '+15553104411', roomNumber: null,
    inHouse: false, stayId: null, smsConsentStatus: 'opted_out', willFail: false,
  },
]

const THREAD = {
  phone: '+15551234567',
  propertyName: 'Harbourview Hotel',
  messages: [
    { id: 'm1', direction: 'outbound', body: 'Welcome to Harbourview, Sarah.', deliveryStatus: 'delivered', sentAt: '2026-09-10T15:22:00Z' },
    { id: 'm2', direction: 'inbound', body: 'Hi, the AC is not working', deliveryStatus: 'delivered', sentAt: '2026-09-10T18:41:00Z' },
  ],
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    const body = url.includes('sim/guests')
      ? GUESTS
      : url.includes('sim/thread')
        ? THREAD
        : url.includes('sim/events')
          ? [{ type: 'message.created', propertyId: 'prop-a', at: '2026-09-10T18:41:07Z', payload: { id: 'm2' } }]
          : []
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  // No SessionProvider on purpose: /sim must work without a login.
  return renderWithProviders(<SimulatorPage />, { route: '/sim' })
}

describe('SimulatorPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders without a session', async () => {
    mount()
    expect(await screen.findByText('Phone simulator')).toBeInTheDocument()
    expect(screen.getByText('DEV ONLY')).toBeInTheDocument()
  })

  it('lists the seeded guests with room and consent state', async () => {
    mount()
    expect(await screen.findByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText(/412/)).toBeInTheDocument()
    expect(screen.getByText('OPTED OUT')).toBeInTheDocument()
  })

  it('flags a number that will fail delivery', async () => {
    mount()
    expect(await screen.findByText('FAILS')).toBeInTheDocument()
    expect(screen.getByText(/0000 fail delivery on purpose/i)).toBeInTheDocument()
  })

  it('loads a thread with both phone and propertyId (ruling R5)', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([u]) => String(u).includes('sim/thread'))
      expect(call).toBeDefined()
      expect(String(call![0])).toContain('propertyId=prop-a')
      expect(String(call![0])).toContain('phone=%2B15551234567')
    })
  })

  it('renders the hotel message as received and the guest message as sent', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    // In the phone we are the guest: outbound (hotel → guest) is the *received* bubble.
    const received = await screen.findByText('Welcome to Harbourview, Sarah.')
    const sent = screen.getByText('Hi, the AC is not working')
    expect(received.closest('[data-testid="sms-in"]')).not.toBeNull()
    expect(sent.closest('[data-testid="sms-out"]')).not.toBeNull()
  })

  it('posts form-encoded Twilio fields with the mock secret', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.type(await screen.findByPlaceholderText(/text as/i), 'Extra towels please')
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }))

    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(String(post[0])).toBe('/api/hooks/sms/inbound')
    const headers = new Headers(post[1]!.headers)
    expect(headers.get('X-Mock-Secret')).toBe('dev')
    const params = new URLSearchParams(String(post[1]!.body))
    expect(params.get('From')).toBe('+15551234567')
    expect(params.get('To')).toBe('+15550100')
    expect(params.get('Body')).toBe('Extra towels please')
    expect(params.get('MessageSid')).toBeTruthy()
  })

  it('sends STOP from the quick button', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(await screen.findByRole('button', { name: 'STOP' }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(new URLSearchParams(String(post[1]!.body)).get('Body')).toBe('STOP')
  })

  it('sends a Luhn-valid card number so redaction actually fires', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(await screen.findByRole('button', { name: /card number/i }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')!
    const sent = new URLSearchParams(String(post[1]!.body)).get('Body')!
    const digits = sent.replace(/\D/g, '')
    // Luhn check — if this fails the server will not redact and the demo is silently broken.
    let sum = 0
    let double = false
    for (let i = digits.length - 1; i >= 0; i--) {
      let d = Number(digits[i])
      if (double) {
        d *= 2
        if (d > 9) d -= 9
      }
      sum += d
      double = !double
    }
    expect(digits.length).toBeGreaterThanOrEqual(13)
    expect(sum % 10).toBe(0)
  })

  it('will not send with no guest selected', async () => {
    mount()
    await screen.findByText('Sarah Chen')
    expect(screen.getByRole('button', { name: /^send$/i })).toBeDisabled()
  })

  it('will not send an empty message', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }))
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })

  it('shows the server event log', async () => {
    mount()
    expect(await screen.findByText(/message\.created/)).toBeInTheDocument()
  })

  it('links to the staff inbox', async () => {
    mount()
    expect(await screen.findByRole('link', { name: /open staff inbox/i })).toHaveAttribute(
      'href',
      '/app/inbox',
    )
  })

  it('disables the PMS buttons with no guest selected', async () => {
    mount()
    await screen.findByText('Sarah Chen')
    expect(screen.getByRole('button', { name: /fire pms check-in/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /fire pms check-out/i })).toBeDisabled()
  })

  it('fires a PMS check-in for the selected guest\'s stay', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(screen.getByRole('button', { name: /fire pms check-in/i }))
    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([u]) => String(u).includes('/pms/check-in/'))
      expect(call).toBeDefined()
      expect(String(call![0])).toBe('/api/dev/pms/check-in/stay-1')
      expect(call![1]?.method).toBe('POST')
    })
  })

  it('fires a PMS check-out for the selected guest\'s stay', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(screen.getByRole('button', { name: /fire pms check-out/i }))
    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([u]) => String(u).includes('/pms/check-out/'))
      expect(call).toBeDefined()
      expect(String(call![0])).toBe('/api/dev/pms/check-out/stay-1')
      expect(call![1]?.method).toBe('POST')
    })
  })

  it('keeps the PMS buttons disabled for a guest with no stay', async () => {
    mount()
    await userEvent.click(await screen.findByText('Lena Park'))
    expect(screen.getByRole('button', { name: /fire pms check-in/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /fire pms check-out/i })).toBeDisabled()
  })

  it('shows a PMS error in its own alert', async () => {
    mount()
    await userEvent.click(await screen.findByText('Sarah Chen'))
    vi.mocked(fetch).mockImplementationOnce(() =>
      Promise.resolve(
        new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Stay not found' } }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    await userEvent.click(screen.getByRole('button', { name: /fire pms check-in/i }))
    expect(await screen.findByText(/check-in error: stay not found/i)).toBeInTheDocument()
  })
})
