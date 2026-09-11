import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { FilterTabs } from './FilterTabs'
import type { Role } from '../../api/types'

function mount(role: Role, onChange = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <FilterTabs value="all" counts={{ all: 23, mine: 6, unassigned: 8, overdue: 3 }} onChange={onChange} />
    </SessionProvider>,
    { session: sessionFixture({ role }) },
  )
  return onChange
}

describe('FilterTabs', () => {
  it('shows the four live filters with their counts for an agent', async () => {
    mount('agent')
    expect(await screen.findByRole('tab', { name: /All 23/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Mine 6/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Unassigned 8/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Overdue 3/ })).toBeInTheDocument()
  })

  it('also offers Snoozed, Resolved and Archived as separate filters (§5.3)', async () => {
    mount('agent')
    expect(await screen.findByRole('tab', { name: /Snoozed/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Resolved/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Archived/ })).toBeInTheDocument()
  })

  it('marks the active tab as selected', async () => {
    mount('agent')
    expect(await screen.findByRole('tab', { name: /All/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /Mine/ })).toHaveAttribute('aria-selected', 'false')
  })

  it('hides All and Unassigned from dept_staff, who cannot view the whole property', async () => {
    mount('dept_staff')
    expect(await screen.findByRole('tab', { name: /Mine/ })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /All/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /Unassigned/ })).not.toBeInTheDocument()
  })

  it('omits a count that has not loaded rather than showing a stale zero', async () => {
    renderWithProviders(
      <SessionProvider>
        <FilterTabs value="all" counts={{}} onChange={vi.fn()} />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    const tab = await screen.findByRole('tab', { name: /All/ })
    expect(tab.textContent).toBe('All')
  })

  it('reports the chosen filter', async () => {
    const onChange = mount('agent')
    await userEvent.click(await screen.findByRole('tab', { name: /Overdue/ }))
    expect(onChange).toHaveBeenCalledWith('overdue')
  })
})
