import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LogEntryOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { AckBar } from './AckBar'

const BASE: LogEntryOut = {
  id: 'log-1',
  authorUserId: 'u-eli',
  authorName: 'Eli Vance',
  body: 'Reminder to check the boiler.',
  createdAt: '2026-09-19T12:00:00Z',
  pinned: false,
  requiresAck: true,
  ackExpectedCount: 5,
  ackedByMe: false,
  canAck: false,
  shift: 'am',
}

function serve() {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify({ ...BASE, ackedByMe: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function mount(entry: LogEntryOut) {
  return renderWithProviders(
    <SessionProvider>
      <AckBar entry={entry} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
}

function postCalls() {
  return vi.mocked(fetch).mock.calls.filter(
    ([input, init]) => String(input).includes('/ack') && init?.method === 'POST',
  )
}

describe('AckBar', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders null when the entry does not require ack', () => {
    const { container } = mount({ ...BASE, requiresAck: false })
    expect(container.firstChild).toBeNull()
  })

  it('shows the acknowledged count against the expected count', () => {
    mount({
      ...BASE,
      ackExpectedCount: 5,
      acks: [
        { userId: 'u-1', name: 'Eli', acknowledgedAt: '2026-09-19T12:05:00Z' },
        { userId: 'u-2', name: 'Sam', acknowledgedAt: '2026-09-19T12:06:00Z' },
      ],
    })
    expect(screen.getByText('2 of 5 acknowledged')).toBeInTheDocument()
  })

  it('shows an enabled Acknowledge button when canAck, and clicking it POSTs once', async () => {
    mount({ ...BASE, canAck: true })
    const button = screen.getByRole('button', { name: 'Acknowledge' })
    expect(button).toBeEnabled()
    await userEvent.click(button)
    expect(postCalls()).toHaveLength(1)
  })

  it('shows an acknowledged message and no button when ackedByMe', () => {
    mount({ ...BASE, ackedByMe: true, canAck: false })
    expect(screen.getByText('You acknowledged this')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
  })

  it('lists outstanding people by name', () => {
    mount({
      ...BASE,
      outstanding: [
        { userId: 'u-3', name: 'Priya Shah' },
        { userId: 'u-4', name: 'Jon Diaz' },
      ],
    })
    expect(screen.getByText(/Priya Shah/)).toBeInTheDocument()
    expect(screen.getByText(/Jon Diaz/)).toBeInTheDocument()
  })

  it('shows no Acknowledge button when the viewer was never asked', () => {
    mount({ ...BASE, canAck: false, ackedByMe: false })
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
  })
})
