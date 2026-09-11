import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'

describe('Button', () => {
  it('is 44px tall and uses the surface treatment by default', () => {
    render(<Button>Assign</Button>)
    expect(screen.getByRole('button', { name: 'Assign' }).className).toContain('h-11')
  })

  it('uses the amber accent only for the primary variant', () => {
    const { rerender } = render(<Button variant="primary">Send</Button>)
    expect(screen.getByRole('button').className).toContain('bg-accent')
    rerender(<Button>Send</Button>)
    expect(screen.getByRole('button').className).not.toContain('bg-accent')
  })

  it('blocks clicks and marks itself busy while loading', async () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Send
      </Button>,
    )
    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('still respects an explicit disabled prop', () => {
    render(<Button disabled>Send</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
