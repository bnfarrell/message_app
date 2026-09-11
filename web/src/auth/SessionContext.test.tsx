import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { SessionProvider, useSession } from './SessionContext'

function Probe() {
  const { user, role, propertyId, can, setPropertyId, logout } = useSession()
  return (
    <div>
      <span data-testid="who">{user.firstName}</span>
      <span data-testid="role">{role}</span>
      <span data-testid="property">{propertyId}</span>
      <span data-testid="can-archive">{String(can('archive'))}</span>
      <button onClick={() => setPropertyId('prop-b')}>switch</button>
      <button onClick={logout}>sign out</button>
    </div>
  )
}

describe('SessionProvider', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('exposes the user, the active membership role and its capabilities', async () => {
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    await waitFor(() => expect(screen.getByTestId('who')).toHaveTextContent('Ava'))
    expect(screen.getByTestId('role')).toHaveTextContent('agent')
    expect(screen.getByTestId('property')).toHaveTextContent('prop-a')
    expect(screen.getByTestId('can-archive')).toHaveTextContent('true')
  })

  it('defaults to the first membership when nothing is stored', async () => {
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent', withSecondProperty: true }) },
    )
    await waitFor(() => expect(screen.getByTestId('property')).toHaveTextContent('prop-a'))
  })

  it('restores a stored active property when it is still a membership', async () => {
    localStorage.setItem('activePropertyId', 'prop-b')
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent', withSecondProperty: true }) },
    )
    await waitFor(() => expect(screen.getByTestId('property')).toHaveTextContent('prop-b'))
  })

  it('ignores a stored property the user no longer has access to', async () => {
    localStorage.setItem('activePropertyId', 'prop-gone')
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    await waitFor(() => expect(screen.getByTestId('property')).toHaveTextContent('prop-a'))
  })

  it('takes the role from the active property, not the first one', async () => {
    localStorage.setItem('activePropertyId', 'prop-b')
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent', withSecondProperty: true, secondRole: 'admin' }) },
    )
    await waitFor(() => expect(screen.getByTestId('role')).toHaveTextContent('admin'))
  })

  it('clears the stored active property on sign-out so it cannot follow the next user', async () => {
    localStorage.setItem('activePropertyId', 'prop-b')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes('/api/auth/logout')
          ? new Response(null, { status: 204 })
          : new Response(
              JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Signed out' } }),
              { status: 401, headers: { 'Content-Type': 'application/json' } },
            ),
      ),
    )
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent', withSecondProperty: true }) },
    )
    await waitFor(() => expect(screen.getByTestId('property')).toHaveTextContent('prop-b'))

    await userEvent.click(screen.getByRole('button', { name: 'sign out' }))

    // A shared front-desk machine: user B must start on B's own first membership, not on
    // whichever property A last looked at.
    await waitFor(() => expect(localStorage.getItem('activePropertyId')).toBeNull())
  })

  it('throws when used outside the provider, so a missing provider fails loudly', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderWithProviders(<Probe />)).toThrow(/SessionProvider/)
    quiet.mockRestore()
  })
})
