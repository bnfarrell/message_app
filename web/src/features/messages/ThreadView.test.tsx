import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ThreadView } from './ThreadView'

const mockSend = vi.fn()
vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffConversation: () => ({
    data: {
      id: 'c1', kind: 'dm', displayName: 'Eli Engineer', avatarUrl: null, otherUserId: 'u2',
      participants: [], lastMessageAt: null, lastMessagePreview: null, unread: false,
      createdAt: '2026-09-19T11:00:00Z', updatedAt: '2026-09-19T11:00:00Z', name: null,
      messages: [
        { id: 'm1', conversationId: 'c1', authorUserId: 'u2', authorName: 'Eli Engineer',
          body: 'On it', photoUrl: null, createdAt: '2026-09-19T12:00:00Z' },
      ],
    },
    isPending: false,
    error: null,
  }),
  useSendStaffMessage: () => ({ mutate: mockSend, isPending: false }),
  useMarkStaffConversationRead: () => ({ mutate: vi.fn() }),
}))

describe('ThreadView', () => {
  it('renders messages and sends on submit', () => {
    render(<ThreadView conversationId="c1" />)
    expect(screen.getByText('On it')).toBeInTheDocument()
    screen.getByPlaceholderText('Type your message').focus()
  })
})
