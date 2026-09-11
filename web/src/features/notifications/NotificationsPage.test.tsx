import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aNotification } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { NotificationsPage } from './NotificationsPage'

function serve(rows: unknown[]) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    const body = String(input).includes('unread-count') ? { count: 2 } : rows
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <NotificationsPage />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: '/app/notifications' },
  )
}

describe('NotificationsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve([aNotification()])
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists notifications with their title and body', async () => {
    mount()
    expect(await screen.findByText('SLA breached in 412')).toBeInTheDocument()
    expect(screen.getByText(/waiting 16 minutes/)).toBeInTheDocument()
  })

  it('marks an unread one visually', async () => {
    mount()
    await screen.findByText('SLA breached in 412')
    expect(screen.getByTestId('unread-dot')).toBeInTheDocument()
  })

  it('does not mark a read one', async () => {
    serve([aNotification({ readAt: '2026-09-10T19:00:00Z' })])
    mount()
    await screen.findByText('SLA breached in 412')
    expect(screen.queryByTestId('unread-dot')).not.toBeInTheDocument()
  })

  it('links a conversation notification to the inbox', async () => {
    mount()
    expect(await screen.findByRole('link', { name: /SLA breached in 412/ })).toHaveAttribute(
      'href',
      '/app/inbox/c-1',
    )
  })

  it('links a work-order notification to the board detail', async () => {
    serve([aNotification({ entityType: 'work_order', entityId: 'w-204', title: 'WO assigned' })])
    mount()
    expect(await screen.findByRole('link', { name: /WO assigned/ })).toHaveAttribute(
      'href',
      '/app/work-orders/w-204',
    )
  })

  it('renders an unlinkable notification as plain text', async () => {
    serve([aNotification({ entityType: null, entityId: null, title: 'Shift handover' })])
    mount()
    await screen.findByText('Shift handover')
    expect(screen.queryByRole('link', { name: /Shift handover/ })).not.toBeInTheDocument()
  })

  it('marks a notification read when it is opened', async () => {
    mount()
    await userEvent.click(await screen.findByRole('link', { name: /SLA breached in 412/ }))
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/notifications/nt-1/read')),
      ).toBe(true),
    )
  })

  it('marks all read', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /mark all read/i }))
    expect(
      vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/notifications/read-all')),
    ).toBe(true)
  })

  it('filters to unread only', async () => {
    mount()
    await screen.findByText('SLA breached in 412')
    await userEvent.click(screen.getByRole('tab', { name: /unread/i }))
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('unread=1'))).toBe(true),
    )
  })

  it('shows an empty state when there is nothing', async () => {
    serve([])
    mount()
    expect(await screen.findByText(/nothing to catch up on/i)).toBeInTheDocument()
  })
})
