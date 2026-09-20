import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DepartmentOut, LogEntryOut, LogFeedOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { LogPage } from './LogPage'

const DEPARTMENTS: DepartmentOut[] = [aDepartment()]

const BASE: LogEntryOut = {
  id: 'log-1',
  authorUserId: 'u-eli',
  authorName: 'Eli Vance',
  body: 'Checked the boiler room.',
  createdAt: new Date().toISOString(),
  pinned: false,
  requiresAck: false,
  ackExpectedCount: 0,
  ackedByMe: false,
  canAck: false,
  shift: 'am',
}

function jsonResponse(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )
}

function serve(feed: LogFeedOut = { entries: [], pinned: [] }) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('mentionables')) return jsonResponse([])
    if (url.includes('/departments')) return jsonResponse(DEPARTMENTS)
    if (url.includes('log-entries')) return jsonResponse(feed)
    return jsonResponse([])
  })
}

function mount(feed?: LogFeedOut) {
  serve(feed)
  return renderWithProviders(
    <SessionProvider>
      <LogPage />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
}

// Excludes the mentionables fetch, which also contains the substring "log-entries".
function feedCalls() {
  return vi
    .mocked(fetch)
    .mock.calls.filter(([input]) => String(input).includes('log-entries') && !String(input).includes('mentionables'))
}

describe('LogPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a tab strip whose only tab is Posts, and it is selected', async () => {
    mount()
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument())
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(1)
    expect(tabs[0]).toHaveTextContent('Posts')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it("groups entries under day headings, reading Today · 2 posts for two entries created today", async () => {
    mount({
      entries: [
        { ...BASE, id: 'log-1' },
        { ...BASE, id: 'log-2' },
      ],
      pinned: [],
    })
    expect(await screen.findByText('Today · 2 posts')).toBeInTheDocument()
  })

  it('renders the pinned block above the day groups, labelled Pinned, when pinned is non-empty', async () => {
    mount({
      entries: [{ ...BASE, id: 'log-1' }],
      pinned: [{ ...BASE, id: 'log-pin', body: 'Pinned notice' }],
    })
    expect(await screen.findByText('Pinned')).toBeInTheDocument()
    expect(screen.getByText('Pinned notice')).toBeInTheDocument()
  })

  it('omits the pinned block entirely when pinned is empty', async () => {
    mount({ entries: [{ ...BASE, id: 'log-1' }], pinned: [] })
    await screen.findByText('Today · 1 post')
    expect(screen.queryByText('Pinned')).not.toBeInTheDocument()
  })

  it('issues a request with shift=overnight when the shift filter changes', async () => {
    mount()
    await waitFor(() => expect(feedCalls().length).toBeGreaterThan(0))

    await userEvent.selectOptions(screen.getByLabelText('Shift'), 'overnight')

    await waitFor(() =>
      expect(feedCalls().some(([input]) => String(input).includes('shift=overnight'))).toBe(true),
    )
  })

  it('issues a request with mentioningMe=true when the Mentioning me toggle is checked', async () => {
    mount()
    await waitFor(() => expect(feedCalls().length).toBeGreaterThan(0))

    await userEvent.click(screen.getByLabelText('Mentioning me'))

    await waitFor(() =>
      expect(feedCalls().some(([input]) => String(input).includes('mentioningMe=true'))).toBe(true),
    )
  })

  it('renders an empty state, not a bare page, for an empty feed', async () => {
    mount({ entries: [], pinned: [] })
    expect(await screen.findByText(/no log entries/i)).toBeInTheDocument()
    expect(screen.queryByText(/·/)).not.toBeInTheDocument()
  })
})
