import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThreadView } from './ThreadView'

const mockSend = vi.fn()
const mockUseSendStaffMessage = vi.fn(() => ({
  mutate: mockSend,
  isPending: false,
  error: null as Error | null,
}))

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
  useSendStaffMessage: () => mockUseSendStaffMessage(),
  useMarkStaffConversationRead: () => ({ mutate: vi.fn() }),
}))

afterEach(() => {
  mockSend.mockClear()
  mockUseSendStaffMessage.mockClear()
  mockUseSendStaffMessage.mockImplementation(() => ({ mutate: mockSend, isPending: false, error: null }))
})

describe('ThreadView', () => {
  it('renders messages and sends a typed draft on submit', async () => {
    render(<ThreadView conversationId="c1" />)
    expect(screen.getByText('On it')).toBeInTheDocument()

    await userEvent.type(screen.getByPlaceholderText('Type your message'), 'Hello there')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(mockSend).toHaveBeenCalledTimes(1)
    expect(mockSend.mock.calls[0]![0]).toEqual({ body: 'Hello there' })
  })

  it('sends an attached photo', async () => {
    render(<ThreadView conversationId="c1" />)
    const file = new File(['bytes'], 'photo.png', { type: 'image/png' })

    await userEvent.upload(screen.getByLabelText('Attach photo'), file)

    expect(mockSend).toHaveBeenCalledTimes(1)
    expect(mockSend.mock.calls[0]![0]).toEqual({ photo: file })
  })

  it('surfaces a send failure', () => {
    mockUseSendStaffMessage.mockImplementation(() => ({
      mutate: mockSend,
      isPending: false,
      error: new Error('Network error'),
    }))

    render(<ThreadView conversationId="c1" />)

    expect(screen.getByRole('alert')).toHaveTextContent('Network error')
  })
})
