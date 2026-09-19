import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StaffConversationOut } from '../../api/types'
import { GroupPanel } from './GroupPanel'

type MutateOpts = { onSuccess?: (value: unknown) => void; onError?: (error: Error) => void }

// `vi.hoisted` so these are initialized before the (hoisted) `vi.mock` factory below
// runs and captures them in its closures.
const {
  mockCreate,
  mockUpdateSpy,
  mockAddSpy,
  mockRemoveSpy,
  mockUseCreateStaffConversation,
  mockUpdateOutcome,
  mockAddOutcome,
  mockRemoveOutcome,
  mockFakeMutationHook,
} = vi.hoisted(() => {
  const mockCreate = vi.fn()
  const mockUpdateSpy = vi.fn()
  const mockAddSpy = vi.fn()
  const mockRemoveSpy = vi.fn()

  const mockUseCreateStaffConversation = vi.fn(() => ({
    mutate: mockCreate,
    isPending: false,
    error: null as Error | null,
  }))

  // Edit-mode tests toggle these to make the fake update/add mutations below succeed or
  // fail, so we can exercise the real sequencing/error-visibility behaviour of `submit()`
  // rather than just asserting a call happened.
  const mockUpdateOutcome = { mode: 'success' as 'success' | 'fail' }
  const mockAddOutcome = { mode: 'success' as 'success' | 'fail' }
  const mockRemoveOutcome = { pending: false }

  /** A minimal fake mutation hook: real `useState` so a mutate() call re-renders the
   * component with the new isPending/error, the way react-query's real hook would. */
  function mockFakeMutationHook(
    spy: (body: unknown) => void,
    outcome: { mode: 'success' | 'fail' },
    failMessage: string,
  ) {
    return function useFake() {
      const [state, setState] = useState<{ isPending: boolean; error: Error | null }>({
        isPending: false,
        error: null,
      })
      function mutate(body: unknown, opts?: MutateOpts) {
        spy(body)
        if (outcome.mode === 'fail') {
          const error = new Error(failMessage)
          setState({ isPending: false, error })
          opts?.onError?.(error)
        } else {
          setState({ isPending: false, error: null })
          opts?.onSuccess?.(body)
        }
      }
      return { mutate, isPending: state.isPending, error: state.error }
    }
  }

  return {
    mockCreate,
    mockUpdateSpy,
    mockAddSpy,
    mockRemoveSpy,
    mockUseCreateStaffConversation,
    mockUpdateOutcome,
    mockAddOutcome,
    mockRemoveOutcome,
    mockFakeMutationHook,
  }
})

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
  useUpdateStaffGroup: mockFakeMutationHook(mockUpdateSpy, mockUpdateOutcome, 'Rename failed'),
  useAddStaffParticipants: mockFakeMutationHook(mockAddSpy, mockAddOutcome, 'Add failed'),
  useRemoveStaffParticipant: () => ({
    mutate: mockRemoveSpy,
    isPending: mockRemoveOutcome.pending,
    error: null,
  }),
}))

const EXISTING: StaffConversationOut = {
  id: 'g1',
  kind: 'group',
  displayName: 'Housekeeping Team',
  avatarUrl: null,
  otherUserId: null,
  name: 'Housekeeping Team',
  participants: [
    { userId: 'u9', firstName: 'Nia', lastName: 'Ward', role: 'dept_staff', departmentId: 'd1', avatarUrl: null },
  ],
  lastMessageAt: null,
  lastMessagePreview: null,
  unread: false,
  createdAt: '2026-09-19T11:00:00Z',
  updatedAt: '2026-09-19T11:00:00Z',
}

afterEach(() => {
  mockCreate.mockClear()
  mockUpdateSpy.mockClear()
  mockAddSpy.mockClear()
  mockRemoveSpy.mockClear()
  mockUseCreateStaffConversation.mockClear()
  mockUseCreateStaffConversation.mockImplementation(() => ({
    mutate: mockCreate,
    isPending: false,
    error: null,
  }))
  mockUpdateOutcome.mode = 'success'
  mockAddOutcome.mode = 'success'
  mockRemoveOutcome.pending = false
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

  it('edit-mode: renames a group and closes once the rename succeeds', async () => {
    const onClose = vi.fn()
    render(<GroupPanel open onClose={onClose} existing={EXISTING} />)

    const nameInput = screen.getByPlaceholderText('Group Name')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'New Name')
    await userEvent.click(screen.getByText('Save'))

    expect(mockUpdateSpy).toHaveBeenCalledWith({ name: 'New Name' })
    expect(mockAddSpy).not.toHaveBeenCalled()
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('edit-mode: renames and adds a member, closing only after both succeed', async () => {
    const onClose = vi.fn()
    render(<GroupPanel open onClose={onClose} existing={EXISTING} />)

    const nameInput = screen.getByPlaceholderText('Group Name')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'New Name')
    await userEvent.click(screen.getByText('Alice Smith'))
    await userEvent.click(screen.getByText('Save'))

    expect(mockUpdateSpy).toHaveBeenCalledWith({ name: 'New Name' })
    await waitFor(() => expect(mockAddSpy).toHaveBeenCalledWith({ userIds: ['u2'] }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('edit-mode: a failed rename blocks the add, keeps the panel open, and shows the error', async () => {
    mockUpdateOutcome.mode = 'fail'
    mockAddOutcome.mode = 'success'
    const onClose = vi.fn()
    render(<GroupPanel open onClose={onClose} existing={EXISTING} />)

    const nameInput = screen.getByPlaceholderText('Group Name')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'New Name')
    await userEvent.click(screen.getByText('Alice Smith'))
    await userEvent.click(screen.getByText('Save'))

    expect(mockUpdateSpy).toHaveBeenCalledWith({ name: 'New Name' })
    expect(mockAddSpy).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Rename failed')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('disables the remove control while a removal is in flight', () => {
    mockRemoveOutcome.pending = true
    render(<GroupPanel open onClose={() => {}} existing={EXISTING} />)

    expect(screen.getByRole('button', { name: 'Remove Nia Ward' })).toBeDisabled()
  })

  it('resets its form state when unmounted on close and remounted (regression: must be conditionally mounted, not just `open`-toggled)', async () => {
    // Mirrors how MessagesPage renders GroupPanel: `{open ? <GroupPanel .../> : null}`,
    // so closing actually unmounts it instead of leaving it mounted with `open={false}`.
    function Wrapper() {
      const [open, setOpen] = useState(true)
      return (
        <>
          <button onClick={() => setOpen(true)}>reopen</button>
          {open ? <GroupPanel open onClose={() => setOpen(false)} /> : null}
        </>
      )
    }

    render(<Wrapper />)

    await userEvent.type(screen.getByPlaceholderText('Group Name'), 'Team')
    await userEvent.click(screen.getByText('Alice Smith'))
    expect(screen.getByText('Alice Smith').closest('button')).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(screen.getByText('Cancel'))
    await userEvent.click(screen.getByText('reopen'))

    expect(screen.getByPlaceholderText('Group Name')).toHaveValue('')
    expect(screen.getByText('Alice Smith').closest('button')).toHaveAttribute('aria-pressed', 'false')
  })
})
