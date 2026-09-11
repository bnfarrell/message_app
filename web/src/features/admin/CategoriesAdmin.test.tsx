import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CategoryOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { CategoriesAdmin } from './CategoriesAdmin'

// Rows are addressed by `cell` role, not by text: once the panel is open its Parent select lists
// every category, so a bare text query matches the <option> as well as the table cell.

const CATEGORIES: CategoryOut[] = [
  { id: 'c-1', name: 'Maintenance', parentId: null, active: true, children: [] },
  { id: 'c-2', name: 'Housekeeping request', parentId: null, active: true, children: [] },
]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function serve() {
  vi.mocked(fetch).mockImplementation((_input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(
      init?.method && init.method !== 'GET' ? json(CATEGORIES[0]) : json(CATEGORIES),
    ),
  )
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <CategoriesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/categories' },
  )
}

describe('CategoriesAdmin — the delete confirmation is scoped to one record', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // This screen refuses a delete with a 409 while the category is still referenced
  // (server/app/domain/categories.py), so arming Delete and then moving on is the normal flow,
  // not an unusual one.
  it('disarms when another row is opened', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Maintenance'))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument()

    await user.click(screen.getByRole('cell', { name: 'Housekeeping request' }))
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Housekeeping request'))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('disarms across a New category, which hides the delete controls without dismissing them', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('Maintenance'))
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    // `onDelete` is undefined for a record that does not exist yet, so the whole delete row
    // disappears and the admin reasonably reads that as the confirmation having been dismissed.
    await user.click(screen.getByRole('button', { name: /new category/i }))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()

    // It must not come back armed on the next saved record the admin opens.
    await user.click(screen.getByRole('cell', { name: 'Housekeeping request' }))
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Housekeeping request'))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })
})
