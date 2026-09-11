import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aQuickReply } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { QuickRepliesAdmin } from './QuickRepliesAdmin'

const REPLIES = [
  aQuickReply({ id: 'q1', shortcut: '/wifi', title: 'WiFi details', usageCount: 212 }),
  aQuickReply({ id: 'q2', shortcut: '/shuttle', title: 'Airport shuttle', active: false, usageCount: 0 }),
]

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    if (init && init.method && init.method !== 'GET') {
      return Promise.resolve(
        new Response(JSON.stringify(aQuickReply()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = String(input).includes('/departments') ? [aDepartment()] : REPLIES
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
      <QuickRepliesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/quick-replies' },
  )
}

describe('QuickRepliesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists replies with shortcut, title and usage', async () => {
    mount()
    expect(await screen.findByText('/wifi')).toBeInTheDocument()
    expect(screen.getByText('WiFi details')).toBeInTheDocument()
    expect(screen.getByText('212')).toBeInTheDocument()
  })

  it('reports the active and inactive counts', async () => {
    mount()
    expect(await screen.findByText(/1 active · 1 inactive/)).toBeInTheDocument()
  })

  it('shows no edit panel until something is selected', async () => {
    mount()
    await screen.findByText('/wifi')
    expect(screen.queryByLabelText('Body')).not.toBeInTheDocument()
  })

  it('opens the edit panel pre-filled when a row is clicked', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await waitFor(() => expect(screen.getByLabelText('Shortcut')).toHaveValue('/wifi'))
    expect(screen.getByLabelText('Title')).toHaveValue('WiFi details')
    expect(screen.getByLabelText('Body')).toHaveValue(REPLIES[0]!.body)
  })

  it('shows usage as read-only text, never as a field', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await waitFor(() => expect(screen.getByText(/212 uses/)).toBeInTheDocument())
    expect(screen.queryByLabelText(/uses/i)).not.toBeInTheDocument()
  })

  it('patches only on save, not on every keystroke', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    const title = await screen.findByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'WiFi info')
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'PATCH')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(String(patch![0])).toContain('/quick-replies/q1')
    expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ title: 'WiFi info' })
  })

  it('creates a new reply through POST', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /new quick reply/i }))
    await userEvent.type(screen.getByLabelText('Shortcut'), '/pool')
    await userEvent.type(screen.getByLabelText('Title'), 'Pool hours')
    await userEvent.type(screen.getByLabelText('Body'), 'The pool is open 7 AM-10 PM.')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({
      shortcut: '/pool',
      title: 'Pool hours',
    })
  })

  it('asks before deleting and only then calls DELETE', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'DELETE')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    const del = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'DELETE')
    expect(String(del![0])).toContain('/quick-replies/q1')
  })

  it('backs out of a delete on Keep', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }))
    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument()
  })

  it('shows the server error in the panel and keeps it open', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await screen.findByLabelText('Title')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ error: { code: 'VALIDATION_FAILED', message: 'Shortcut already exists' } }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Shortcut already exists')
    expect(screen.getByLabelText('Title')).toBeInTheDocument()
  })

  it('filters by shortcut or text', async () => {
    mount()
    await screen.findByText('/wifi')
    await userEvent.type(screen.getByPlaceholderText(/search/i), 'shuttle')
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('q=shuttle'))).toBe(true),
    )
  })

  // Regression test for the invalidation-key trap: qk.quickReplies(propertyId) with no search
  // term produces a key that does not match a search-filtered key. If a mutation invalidated
  // that exact key instead of the `quickRepliesAll` prefix, an edit made while a search filter
  // is active would save but the filtered list would never refetch — with no error anywhere.
  it('refreshes a search-filtered list after an edit made under that filter', async () => {
    mount()
    await screen.findByText('/wifi')
    await userEvent.type(screen.getByPlaceholderText(/search/i), 'shuttle')
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('q=shuttle'))).toBe(true),
    )
    const filteredGets = () =>
      vi
        .mocked(fetch)
        .mock.calls.filter(
          ([u, i]) => (!i || !i.method || i.method === 'GET') && String(u).includes('q=shuttle'),
        ).length
    const before = filteredGets()

    await userEvent.click(await screen.findByText('WiFi details'))
    const title = await screen.findByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'WiFi info')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    // A save that only invalidated the exact (unfiltered) key would never re-fetch the
    // still-active filtered query, so `filteredGets()` would stay flat at `before`.
    await waitFor(() => expect(filteredGets()).toBeGreaterThan(before))
  })
})
