import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { aMessage } from '../../test/factories'
import { MessageBubble } from './MessageBubble'

describe('MessageBubble', () => {
  it('renders an inbound guest message on the left with the surface treatment', () => {
    render(<MessageBubble message={aMessage()} authorName={null} />)
    const bubble = screen.getByTestId('bubble')
    expect(bubble.className).toContain('bg-surface2')
    expect(screen.getByTestId('bubble-row').className).toContain('justify-start')
  })

  it('renders an outbound staff message on the right with the outbound treatment', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', authorType: 'staff', authorUserId: 'u-ava' })}
        authorName="Ava"
      />,
    )
    expect(screen.getByTestId('bubble').className).toContain('bg-outBg')
    expect(screen.getByTestId('bubble-row').className).toContain('justify-end')
    expect(screen.getByText(/Ava/)).toBeInTheDocument()
  })

  it('labels an automated message', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', authorType: 'automation' })}
        authorName={null}
      />,
    )
    expect(screen.getByText('Automatic')).toBeInTheDocument()
    expect(screen.getByTestId('bubble').className).toContain('bg-autoBg')
  })

  it('shows a redaction chip when the card number was masked (§6)', () => {
    render(
      <MessageBubble
        message={aMessage({ redacted: true, body: 'my card is **** **** **** 1234' })}
        authorName={null}
      />,
    )
    expect(screen.getByText('Card number redacted')).toBeInTheDocument()
  })

  it('shows Sending… while queued', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', deliveryStatus: 'queued', sentAt: null })}
        authorName="Ava"
      />,
    )
    expect(screen.getByText('Sending…')).toBeInTheDocument()
  })

  it('shows Delivered once delivered', () => {
    render(
      <MessageBubble
        message={aMessage({ direction: 'outbound', deliveryStatus: 'delivered' })}
        authorName="Ava"
      />,
    )
    expect(screen.getByText('Delivered')).toBeInTheDocument()
  })

  it('shows the provider error and a retry affordance on failure', () => {
    render(
      <MessageBubble
        message={aMessage({
          direction: 'outbound',
          deliveryStatus: 'failed',
          providerErrorCode: '30007',
          providerErrorMessage: 'Carrier rejected',
        })}
        authorName="Ava"
        onRetry={() => {}}
      />,
    )
    const failure = screen.getByText(/Failed/)
    expect(failure.className).toContain('dangerText')
    expect(screen.getByText(/30007/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('shows no delivery status on an inbound message — the guest sent it', () => {
    render(<MessageBubble message={aMessage()} authorName={null} />)
    expect(screen.queryByText('Delivered')).not.toBeInTheDocument()
  })
})
