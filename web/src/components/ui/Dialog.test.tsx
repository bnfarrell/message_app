import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Dialog } from './Dialog'

function open(onClose = vi.fn()) {
  render(
    <Dialog open onClose={onClose} title="Create work order">
      <input aria-label="Title" />
      <button>Save</button>
    </Dialog>,
  )
  return onClose
}

describe('Dialog', () => {
  it('renders nothing when closed', () => {
    render(
      <Dialog open={false} onClose={vi.fn()} title="Create work order">
        body
      </Dialog>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('is a labelled modal dialog when open', () => {
    open()
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Create work order')
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
  })

  it('moves focus into the dialog so keyboard users are not left on the page behind', async () => {
    open()
    await vi.waitFor(() =>
      expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true),
    )
  })

  it('closes on Escape', async () => {
    const onClose = open()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('closes on a backdrop click but not on a click inside the panel', async () => {
    const onClose = open()
    await userEvent.click(screen.getByTestId('dialog-backdrop'))
    expect(onClose).toHaveBeenCalledOnce()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
