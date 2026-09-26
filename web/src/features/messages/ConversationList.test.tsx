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
      {
        id: 'g1',
        kind: 'group',
        displayName: 'Housekeeping Team',
        avatarUrl: null,
        otherUserId: null,
        lastMessagePreview: null,
        unread: false,
        participants: [],
        lastMessageAt: null,
        createdAt: '2026-09-19T11:00:00Z',
        updatedAt: '2026-09-19T11:00:00Z',
        name: 'Housekeeping Team',
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

  it('shows only conversations whose name matches the filter', () => {
    renderWithProviders(<ConversationList onSelect={() => {}} filter="housekeep" />)
    expect(screen.getByText('Housekeeping Team')).toBeInTheDocument()
    expect(screen.queryByText('Eli Engineer')).not.toBeInTheDocument()
  })

  it('says so when the filter matches no conversation', () => {
    renderWithProviders(<ConversationList onSelect={() => {}} filter="zzz" />)
    expect(screen.getByText('No conversations match')).toBeInTheDocument()
    expect(screen.queryByText('Eli Engineer')).not.toBeInTheDocument()
  })
})
