import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversationDetail } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ArchiveDialog } from './ArchiveDialog'

const CATEGORIES = [
  {
    id: 'cat-maint',
    name: 'Maintenance',
    parentId: null,
    active: true,
    children: [
      { id: 'cat-hvac', name: 'HVAC', parentId: 'cat-maint', active: true, children: [] },
      { id: 'cat-plumb', name: 'Plumbing', parentId: 'cat-maint', active: true, children: [] },
    ],
  },
  { id: 'cat-praise', name: 'Praise', parentId: null, active: true, children: [] },
]

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PATCH') {
      return Promise.resolve(
        new Response(JSON.stringify(aConversationDetail({ status: 'archived' })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    return Promise.resolve(
      new Response(JSON.stringify(url.includes('resolution-categories') ? CATEGORIES : []), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(onClose = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <ArchiveDialog conversationId="c-1" open onClose={onClose} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
  return onClose
}

describe('ArchiveDialog', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('offers the category tree flattened, parents and children', async () => {
    mount()
    const select = await screen.findByLabelText(/resolution category/i)
    await waitFor(() => expect(select).toHaveDisplayValue('—'))
    expect(screen.getByRole('option', { name: 'Maintenance' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /HVAC/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Praise' })).toBeInTheDocument()
  })

  it('archives with no category, because the category is optional (§5.3)', async () => {
    mount()
    await screen.findByLabelText(/resolution category/i)
    await userEvent.click(screen.getByRole('button', { name: /archive/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({
      status: 'archived',
      resolutionCategoryId: null,
    })
  })

  it('archives with the chosen category', async () => {
    mount()
    const select = await screen.findByLabelText(/resolution category/i)
    await waitFor(() => expect(screen.getByRole('option', { name: /HVAC/ })).toBeInTheDocument())
    await userEvent.selectOptions(select, 'cat-hvac')
    await userEvent.click(screen.getByRole('button', { name: /archive/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ resolutionCategoryId: 'cat-hvac' })
  })

  it('closes on success', async () => {
    const onClose = mount()
    await screen.findByLabelText(/resolution category/i)
    await userEvent.click(screen.getByRole('button', { name: /archive/i }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})
