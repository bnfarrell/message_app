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

  it('lists the six live sections as links, in the order the mockup uses', async () => {
    mount()
    const labels = [
      'Users & roles',
      'Departments',
      'Quick replies',
      'Digital assets',
      'Resolution categories',
      // Sixth and last of the live group, directly above the divider — where Admin.dc.html
      // draws it, and it draws it ungreyed, so this is the client catching up to the mockup.
      'Property settings',
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
    for (const name of ['Automations', 'Blocked numbers', 'Integrations']) {
      expect(screen.getByText(name)).toBeInTheDocument()
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument()
    }
    // The three that stay greyed have no models, no endpoints and no spec behind them; the
    // caption above them is unchanged.
    expect(screen.getByText(/arrive in Phase 2/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Property settings' })).toBeInTheDocument()
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

  it('routes to the departments screen, which is now editable', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            id: 'd-1',
            // Not "Housekeeping": the Type column now renders a human label, so a name equal to
            // its own type label would match twice and prove nothing about either.
            name: 'Rooms',
            type: 'housekeeping',
            escalationMinutes: 20,
            active: true,
          },
        ]),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    mount('/app/admin/departments')

    expect(await screen.findByText('Rooms')).toBeInTheDocument()
    expect(screen.getByText('Housekeeping')).toBeInTheDocument()
    expect(screen.getByText('20 min')).toBeInTheDocument()
    // A1 added POST/PATCH/DELETE, so the screen that used to be read-only "by design" now
    // offers a way in. What it does with it is DepartmentsAdmin.test.tsx's subject.
    expect(screen.getByRole('button', { name: /new department/i })).toBeInTheDocument()
  })
})
