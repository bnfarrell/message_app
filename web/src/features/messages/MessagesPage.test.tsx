import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MessagesPage } from './MessagesPage'

const { mockCreateDm, mockCreateDmState, threadMounts } = vi.hoisted(() => ({
  mockCreateDm: vi.fn(),
  mockCreateDmState: { error: null as Error | null },
  threadMounts: { count: 0 },
}))

vi.mock('./ConversationList', () => ({
  ConversationList: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <div>
      <button onClick={() => onSelect('c1')}>pick c1</button>
      <button onClick={() => onSelect('g1')}>pick g1</button>
    </div>
  ),
}))
vi.mock('./NewConversationList', () => ({
  NewConversationList: ({ onStart }: { onStart: (userId: string) => void }) => (
    <button onClick={() => onStart('u9')}>start u9</button>
  ),
}))
vi.mock('./ThreadView', () => ({
  ThreadView: ({
    conversationId,
    onManageGroup,
  }: {
    conversationId: string
    onManageGroup?: () => void
  }) => {
    // Tracks distinct mounts (not re-renders): if MessagesPage remounts ThreadView on a
    // conversation switch (via `key`), this instance number changes; if it only re-renders
    // the same instance with a new conversationId prop, the number stays put.
    const [instance] = useState(() => ++threadMounts.count)
    return (
      <div>
        <div>
          thread-{conversationId} instance-{instance}
        </div>
        {onManageGroup ? <button onClick={onManageGroup}>manage group</button> : null}
      </div>
    )
  },
}))
vi.mock('./GroupPanel', () => ({
  GroupPanel: ({
    open,
    existing,
    onSelfRemoved,
  }: {
    open: boolean
    existing?: { id: string }
    onSelfRemoved?: () => void
  }) =>
    open ? (
      <div>
        <div>{existing ? `managing-${existing.id}` : 'creating-group'}</div>
        {onSelfRemoved ? <button onClick={onSelfRemoved}>simulate self removal</button> : null}
      </div>
    ) : null,
}))
vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffConversations: () => ({
    data: [
      {
        id: 'c1',
        kind: 'dm',
        displayName: 'Eli Engineer',
        otherUserId: 'u2',
        participants: [],
        lastMessageAt: null,
        lastMessagePreview: null,
        unread: false,
        createdAt: '2026-09-19T11:00:00Z',
        updatedAt: '2026-09-19T11:00:00Z',
        name: null,
      },
      {
        id: 'g1',
        kind: 'group',
        displayName: 'Housekeeping Team',
        otherUserId: null,
        participants: [],
        lastMessageAt: null,
        lastMessagePreview: null,
        unread: false,
        createdAt: '2026-09-19T11:00:00Z',
        updatedAt: '2026-09-19T11:00:00Z',
        name: 'Housekeeping Team',
      },
    ],
    isPending: false,
    error: null,
  }),
  useCreateStaffConversation: () => ({
    mutate: mockCreateDm,
    isPending: false,
    error: mockCreateDmState.error,
  }),
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/app/messages" element={<MessagesPage />} />
        <Route path="/app/messages/:id" element={<MessagesPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('MessagesPage', () => {
  beforeEach(() => {
    mockCreateDm.mockReset()
    mockCreateDmState.error = null
    threadMounts.count = 0
  })

  it('shows no thread until one is selected', () => {
    renderAt('/app/messages')
    expect(screen.queryByText(/thread-/)).not.toBeInTheDocument()
  })

  it('shows the thread named by the route param', () => {
    renderAt('/app/messages/c1')
    expect(screen.getByText('thread-c1 instance-1')).toBeInTheDocument()
  })

  it('navigates to the conversation route when one is selected from the list', async () => {
    renderAt('/app/messages')
    await userEvent.click(screen.getByText('pick c1'))
    expect(await screen.findByText(/thread-c1/)).toBeInTheDocument()
  })

  it('starts a DM from NewConversationList and navigates to the created conversation', async () => {
    mockCreateDm.mockImplementation((_body, opts) => {
      opts?.onSuccess?.({ id: 'new-dm' })
    })
    renderAt('/app/messages')
    await userEvent.click(screen.getByText('start u9'))
    expect(mockCreateDm).toHaveBeenCalledWith({ kind: 'dm', userId: 'u9' }, expect.anything())
    expect(await screen.findByText(/thread-new-dm/)).toBeInTheDocument()
  })

  it('surfaces a failed DM-creation attempt', () => {
    mockCreateDmState.error = new Error('Could not start conversation')
    renderAt('/app/messages')
    expect(screen.getByRole('alert')).toHaveTextContent('Could not start conversation')
  })

  it('remounts ThreadView instead of just updating props when switching conversations', async () => {
    renderAt('/app/messages/c1')
    expect(screen.getByText('thread-c1 instance-1')).toBeInTheDocument()

    await userEvent.click(screen.getByText('pick g1'))

    // A fresh instance number proves ThreadView was remounted (its internal state, such
    // as scroll position or composer draft, is reset), not merely re-rendered in place.
    expect(await screen.findByText('thread-g1 instance-2')).toBeInTheDocument()
  })

  it('opens the group-management panel for a group conversation and handles self-removal', async () => {
    renderAt('/app/messages/g1')
    await userEvent.click(screen.getByText('manage group'))
    expect(screen.getByText('managing-g1')).toBeInTheDocument()

    await userEvent.click(screen.getByText('simulate self removal'))

    // Leaving a group means the thread route now 404s for this user, so the page should
    // stop showing it and close the management panel.
    expect(screen.queryByText('managing-g1')).not.toBeInTheDocument()
    expect(screen.queryByText(/thread-g1/)).not.toBeInTheDocument()
  })
})
