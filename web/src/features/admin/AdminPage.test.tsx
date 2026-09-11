import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { AdminPage } from './AdminPage'

function mount(route = '/app/admin/quick-replies') {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/admin/*" element={<AdminPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route },
  )
}

describe('AdminPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    ))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists the four live sections as links', async () => {
    mount()
    for (const name of ['Users & roles', 'Quick replies', 'Digital assets', 'Resolution categories']) {
      expect(await screen.findByRole('link', { name })).toBeInTheDocument()
    }
  })

  it('lists the Phase 2 sections as disabled, not as links', async () => {
    mount()
    await screen.findByRole('link', { name: 'Quick replies' })
    for (const name of ['Departments', 'Property settings', 'Automations', 'Blocked numbers', 'Integrations']) {
      expect(screen.getByText(name)).toBeInTheDocument()
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument()
    }
    expect(screen.getByText(/arrive in Phase 2/i)).toBeInTheDocument()
  })

  it('marks the current section', async () => {
    mount('/app/admin/users')
    expect(await screen.findByRole('link', { name: 'Users & roles' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('redirects a bare /app/admin to users', async () => {
    mount('/app/admin')
    expect(await screen.findByRole('link', { name: 'Users & roles' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
