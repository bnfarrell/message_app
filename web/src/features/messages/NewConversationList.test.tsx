import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../../test/harness'
import { NewConversationList } from './NewConversationList'

vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffDirectory: () => ({
    data: [
      { userId: 'u1', firstName: 'Rosa', lastName: 'Lima', role: 'dept_staff',
        departmentName: 'Housekeeping', avatarUrl: null },
      { userId: 'u2', firstName: 'José', lastName: 'Ruiz', role: 'agent',
        departmentName: 'Front Desk', avatarUrl: null },
    ],
    isPending: false,
    error: null,
  }),
}))

describe('NewConversationList', () => {
  it('filters the directory by full name', () => {
    renderWithProviders(<NewConversationList excludeUserIds={[]} onStart={() => {}} filter="rosa l" />)
    expect(screen.getByText('Rosa Lima')).toBeInTheDocument()
    expect(screen.queryByText('José Ruiz')).not.toBeInTheDocument()
  })

  it('matches without accents', () => {
    renderWithProviders(<NewConversationList excludeUserIds={[]} onStart={() => {}} filter="jose" />)
    expect(screen.getByText('José Ruiz')).toBeInTheDocument()
    expect(screen.queryByText('Rosa Lima')).not.toBeInTheDocument()
  })

  it('says so when the filter matches nobody', () => {
    renderWithProviders(<NewConversationList excludeUserIds={[]} onStart={() => {}} filter="zzz" />)
    expect(screen.getByText('No staff match')).toBeInTheDocument()
  })

  it('renders nothing when everyone already has a DM and no filter is set', () => {
    const { container } = renderWithProviders(
      <NewConversationList excludeUserIds={['u1', 'u2']} onStart={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
