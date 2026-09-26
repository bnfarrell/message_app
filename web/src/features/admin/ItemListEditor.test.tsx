import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { ItemListEditor, type ItemDraft } from './ItemListEditor'

function Harness({ initial = [] as ItemDraft[] }) {
  const [items, setItems] = useState(initial)
  return (
    <>
      <ItemListEditor items={items} onChange={setItems} />
      <output data-testid="labels">{items.map((i) => i.label).join('|')}</output>
    </>
  )
}

const saved: ItemDraft = { id: 'i-1', label: 'Pool pH', itemType: 'number', unit: '',
  minValue: '7.2', maxValue: '7.8', required: true }

describe('ItemListEditor', () => {
  it('adds an item and shows bounds only for numbers', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Add item' }))
    await user.type(screen.getByLabelText('Label for item 1'), 'Boiler temp')
    expect(screen.queryByLabelText('Min for item 1')).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Type for item 1'), 'number')
    expect(screen.getByLabelText('Min for item 1')).toBeInTheDocument()
    expect(screen.getByTestId('labels')).toHaveTextContent('Boiler temp')
  })

  it('locks the type of a saved item, and reorders and removes', async () => {
    const user = userEvent.setup()
    render(<Harness initial={[saved, { ...saved, id: 'i-2', label: 'Chlorine' }]} />)
    expect(screen.getByLabelText('Type for item 1')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Move item 2 up' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Chlorine|Pool pH')
    await user.click(screen.getByRole('button', { name: 'Remove item 1' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Pool pH')
  })
})
