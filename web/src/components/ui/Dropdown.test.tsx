import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Dropdown } from './Dropdown'

function setup() {
  render(
    <Dropdown label="Assign">
      {(close) => (
        <button role="menuitem" onClick={close}>
          Ava
        </button>
      )}
    </Dropdown>,
  )
}

describe('Dropdown', () => {
  it('starts closed and reports its state to assistive tech', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Assign' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('opens on click and renders its items in a menu', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Ava' })).toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the trigger', async () => {
    setup()
    const trigger = screen.getByRole('button', { name: 'Assign' })
    await userEvent.click(trigger)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('closes when an item calls the close callback it is handed', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await userEvent.click(screen.getByRole('menuitem', { name: 'Ava' }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('closes on an outside click', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await userEvent.click(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
