import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversationDetail, aGuest } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { GuestPanel } from './GuestPanel'
import { aWorkOrder, aDraftPrompt, aNote } from '../../test/factories'

function mount(detail = aConversationDetail()) {
  return renderWithProviders(
    <SessionProvider>
      <GuestPanel conversation={detail} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: '/app/inbox/c-1' },
  )
}

describe('GuestPanel', () => {
  it('shows the guest identity and phone in mono', async () => {
    mount()
    expect(await screen.findByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText('+15551234567').className).toContain('font-mono')
  })

  it('shows the stay: room, type, dates and stay count', async () => {
    mount()
    expect(await screen.findByText('412 · King')).toBeInTheDocument()
    expect(screen.getByText(/2026-09-09/)).toBeInTheDocument()
    expect(screen.getByText(/4th stay/i)).toBeInTheDocument()
  })

  it('shows consent status as a green chip when opted in', async () => {
    mount()
    const chip = await screen.findByText('Opted in')
    expect(chip.className).toContain('okText')
  })

  it('shows consent status as a red chip when opted out', async () => {
    mount(aConversationDetail({ guest: aGuest({ smsConsentStatus: 'opted_out' }) }))
    const chip = await screen.findByText('Opted out')
    expect(chip.className).toContain('dangerText')
  })

  it('lists open work orders with a link to each', async () => {
    mount(aConversationDetail({ workOrders: [aWorkOrder({ id: 'w-204', title: 'AC not cooling' })] }))
    const link = await screen.findByRole('link', { name: /AC not cooling/ })
    expect(link).toHaveAttribute('href', '/app/work-orders/w-204')
  })

  it('reports pending draft prompts', async () => {
    mount(aConversationDetail({ draftPrompts: [aDraftPrompt()] }))
    expect(await screen.findByText(/1 pending prompt/i)).toBeInTheDocument()
  })

  it('lists recent notes', async () => {
    mount(aConversationDetail({ notes: [aNote({ body: 'Guest is Gold, 4th stay.' })] }))
    expect(await screen.findByText('Guest is Gold, 4th stay.')).toBeInTheDocument()
  })

  it('handles a guest with no stay without crashing', async () => {
    mount(aConversationDetail({ stay: null, guest: aGuest({ firstName: null, lastName: null }) }))
    expect(await screen.findByText('No stay on file')).toBeInTheDocument()
  })
})
