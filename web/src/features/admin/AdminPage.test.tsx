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

  it('lists the five live sections as links, in the order the mockup uses', async () => {
    mount()
    const labels = [
      'Users & roles',
      'Departments',
      'Quick replies',
      'Digital assets',
      'Resolution categories',
    ]
    for (const name of labels) {
      expect(await screen.findByRole('link', { name })).toBeInTheDocument()
    }
    // Admin.dc.html puts Departments second, directly under Users & roles.
    const rendered = screen.getAllByRole('link').map((link) => link.textContent)
    expect(rendered.slice(0, labels.length)).toEqual(labels)
  })

  it('lists the Phase 2 sections as disabled, not as links', async () => {
    mount()
    await screen.findByRole('link', { name: 'Quick replies' })
    for (const name of ['Property settings', 'Automations', 'Blocked numbers', 'Integrations']) {
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

  it('shows departments read-only: the rows are there and there is no create button', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            id: 'd-1',
            name: 'Housekeeping',
            type: 'housekeeping',
            escalationMinutes: 20,
            active: true,
          },
        ]),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    mount('/app/admin/departments')

    expect(await screen.findByText('Housekeeping')).toBeInTheDocument()
    expect(screen.getByText('20 min')).toBeInTheDocument()
    // Phase 1 exposes only the GET, so the screen must offer no way to write.
    expect(screen.queryByRole('button', { name: /new department/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument()
  })
})
