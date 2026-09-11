import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { SessionProvider, useSession } from './SessionContext'

function Probe() {
  const { user, role, propertyId, can, setPropertyId } = useSession()
  return (
    <div>
      <span data-testid="who">{user.firstName}</span>
      <span data-testid="role">{role}</span>
      <span data-testid="property">{propertyId}</span>
      <span data-testid="can-archive">{String(can('archive'))}</span>
      <button onClick={() => setPropertyId('prop-b')}>switch</button>
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

  it('throws when used outside the provider, so a missing provider fails loudly', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderWithProviders(<Probe />)).toThrow(/SessionProvider/)
    quiet.mockRestore()
  })
})
