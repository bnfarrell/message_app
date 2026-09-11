import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aAsset, aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { AssetsAdmin } from './AssetsAdmin'

const ASSETS = [
  aAsset({ id: 'a-1', name: 'WiFi card', shortCode: 'wifi1' }),
  aAsset({ id: 'a-2', name: 'Breakfast menu', shortCode: 'brek1', type: 'menu' }),
]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method && init.method !== 'GET') return Promise.resolve(json(aAsset()))
    if (String(input).includes('/departments')) return Promise.resolve(json([aDepartment()]))
    return Promise.resolve(json(ASSETS))
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <AssetsAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/assets' },
  )
}

describe('AssetsAdmin — the delete confirmation is scoped to one record', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('disarms when another row is opened', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi card'))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument()

    await user.click(screen.getByText('Breakfast menu'))
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Breakfast menu'))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('disarms across a New asset, which hides the delete controls without dismissing them', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText('WiFi card'))
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    // The delete row vanishes because `onDelete` is undefined for an unsaved record. Nothing on
    // screen says the arming survived it.
    await user.click(screen.getByRole('button', { name: /new asset/i }))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()

    await user.click(screen.getByText('Breakfast menu'))
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Breakfast menu'))
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })
})
