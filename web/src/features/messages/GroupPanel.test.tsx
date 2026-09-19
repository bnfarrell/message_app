import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GroupPanel } from './GroupPanel'

const mockCreate = vi.fn()
const mockUpdate = vi.fn()
const mockAdd = vi.fn()
const mockRemove = vi.fn()

const mockUseCreateStaffConversation = vi.fn(() => ({ mutate: mockCreate, isPending: false, error: null as Error | null }))

vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffDirectory: () => ({
    data: [
      {
        userId: 'u2',
        firstName: 'Alice',
        lastName: 'Smith',
        avatarUrl: null,
        role: 'dept_staff',
        departmentId: 'd1',
        departmentName: 'Housekeeping',
      },
    ],
    isPending: false,
    error: null,
  }),
  useCreateStaffConversation: () => mockUseCreateStaffConversation(),
  useUpdateStaffGroup: () => ({ mutate: mockUpdate, isPending: false, error: null }),
  useAddStaffParticipants: () => ({ mutate: mockAdd, isPending: false, error: null }),
  useRemoveStaffParticipant: () => ({ mutate: mockRemove, isPending: false, error: null }),
}))

afterEach(() => {
  mockCreate.mockClear()
  mockUpdate.mockClear()
  mockAdd.mockClear()
  mockRemove.mockClear()
  mockUseCreateStaffConversation.mockClear()
  mockUseCreateStaffConversation.mockImplementation(() => ({
    mutate: mockCreate,
    isPending: false,
    error: null,
  }))
})

describe('GroupPanel', () => {
  it('creates a group with a name and selected members', async () => {
    render(<GroupPanel open onClose={() => {}} />)

    await userEvent.type(screen.getByPlaceholderText('Group Name'), 'Team')
    await userEvent.click(screen.getByText('Alice Smith'))
    await userEvent.click(screen.getByText('Create'))

    expect(mockCreate).toHaveBeenCalledWith(
      { kind: 'group', name: 'Team', userIds: ['u2'] },
      expect.anything(),
    )
  })

  it('surfaces a create failure', () => {
    mockUseCreateStaffConversation.mockImplementation(() => ({
      mutate: mockCreate,
      isPending: false,
      error: new Error('Network error'),
    }))

    render(<GroupPanel open onClose={() => {}} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Network error')
  })
})
