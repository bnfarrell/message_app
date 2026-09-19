import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../../test/harness'
import { ConversationList } from './ConversationList'

vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffConversations: () => ({
    data: [
      {
        id: 'c1',
        kind: 'dm',
        displayName: 'Eli Engineer',
        avatarUrl: null,
        otherUserId: 'u2',
        lastMessagePreview: 'AC is out',
        unread: true,
        participants: [],
        lastMessageAt: '2026-09-19T12:00:00Z',
        createdAt: '2026-09-19T11:00:00Z',
        updatedAt: '2026-09-19T12:00:00Z',
        name: null,
      },
    ],
    isPending: false,
    error: null,
  }),
}))

describe('ConversationList', () => {
  it('shows an unread indicator for an unread conversation', () => {
    renderWithProviders(<ConversationList onSelect={() => {}} />)
    expect(screen.getByText('Eli Engineer')).toBeInTheDocument()
    expect(screen.getByText('AC is out')).toBeInTheDocument()
    expect(screen.getByTestId('unread-dot')).toBeInTheDocument()
  })
})
