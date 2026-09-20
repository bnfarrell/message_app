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

/** Serves `pages` in order to successive log-entries requests, so a test can walk
 *  the cursor. The last page is repeated if anything asks for more. */
function servePages(pages: LogFeedOut[]) {
  let next = 0
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('mentionables')) return jsonResponse([])
    if (url.includes('/departments')) return jsonResponse(DEPARTMENTS)
    if (url.includes('log-entries')) {
      const page = pages[Math.min(next, pages.length - 1)]!
      next += 1
      return jsonResponse(page)
    }
    return jsonResponse([])
  })
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

  describe('pagination', () => {
    const PINNED: LogEntryOut = { ...BASE, id: 'log-pin', body: 'Pinned notice.', pinned: true }
    const PAGE_ONE: LogFeedOut = {
      pinned: [PINNED],
      entries: [{ ...BASE, id: 'log-a', body: 'First page entry.' }],
      nextCursor: '2026-09-19T10:00:00+00:00|log-a',
    }
    // The server returns the SAME pinned block on every page — it is unpaginated by
    // design — so the page must take pinned from page 0 only.
    const PAGE_TWO: LogFeedOut = {
      pinned: [PINNED],
      entries: [{ ...BASE, id: 'log-b', body: 'Second page entry.' }],
      nextCursor: null,
    }

    it('loads older entries and keeps both pages, newest first', async () => {
      servePages([PAGE_ONE, PAGE_TWO])
      expect(await screen.findByText('First page entry.')).toBeInTheDocument()
      expect(screen.queryByText('Second page entry.')).not.toBeInTheDocument()

      await userEvent.click(screen.getByRole('button', { name: /load more/i }))

      expect(await screen.findByText('Second page entry.')).toBeInTheDocument()
      expect(screen.getByText('First page entry.')).toBeInTheDocument()
    })

    it('sends the cursor from the previous page on the follow-up request', async () => {
      servePages([PAGE_ONE, PAGE_TWO])
      await screen.findByText('First page entry.')
      await userEvent.click(screen.getByRole('button', { name: /load more/i }))

      await waitFor(() =>
        expect(
          feedCalls().some(([input]) =>
            String(input).includes(`cursor=${encodeURIComponent(PAGE_ONE.nextCursor!)}`),
          ),
        ).toBe(true),
      )
    })

    it('renders the pinned block once, not once per loaded page', async () => {
      servePages([PAGE_ONE, PAGE_TWO])
      await screen.findByText('First page entry.')
      await userEvent.click(screen.getByRole('button', { name: /load more/i }))
      await screen.findByText('Second page entry.')

      expect(screen.getAllByText('Pinned notice.')).toHaveLength(1)
    })

    it('hides Load more once the last page has no cursor', async () => {
      servePages([PAGE_ONE, PAGE_TWO])
      await screen.findByText('First page entry.')
      await userEvent.click(screen.getByRole('button', { name: /load more/i }))
      await screen.findByText('Second page entry.')

      expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument()
    })

    it('shows no Load more when the first page is already the last', async () => {
      mount({ pinned: [], entries: [{ ...BASE, id: 'log-a' }], nextCursor: null })
      await screen.findByText('Checked the boiler room.')
      expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument()
    })
  })
})
