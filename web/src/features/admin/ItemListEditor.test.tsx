import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { ItemListEditor, orderByCategory, type CategoryOption, type ItemDraft } from './ItemListEditor'

function Harness({ initial = [] as ItemDraft[], categories }: {
  initial?: ItemDraft[]
  categories?: CategoryOption[]
}) {
  const [items, setItems] = useState(initial)
  return (
    <>
      <ItemListEditor items={items} onChange={setItems} categories={categories} />
      <output data-testid="labels">{items.map((i) => i.label).join('|')}</output>
      <output data-testid="groups">{items.map((i) => i.categoryKey ?? '-').join('|')}</output>
    </>
  )
}

const saved: ItemDraft = { id: 'i-1', label: 'Pool pH', itemType: 'number', unit: '',
  minValue: '7.2', maxValue: '7.8', required: true }

const CATEGORIES: CategoryOption[] = [{ key: 'c-audit', name: 'Audit' }, { key: 'c-pay', name: 'Payments' }]
const check = (id: string, label: string, categoryKey: string | null): ItemDraft => ({
  id, label, itemType: 'checkbox', unit: '', minValue: '', maxValue: '', required: true, categoryKey,
})

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

  it('has no category control when no categories are passed (PM)', () => {
    render(<Harness initial={[saved]} />)
    expect(screen.queryByLabelText('Category for item 1')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument()
  })

  it('groups items under their category headings, ungrouped first', () => {
    render(<Harness categories={CATEGORIES} initial={[
      check('a', 'Card batch', 'c-pay'), check('b', 'Notes', null), check('c', 'Audit run', 'c-audit'),
    ]} />)
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['Audit', 'Payments'])
    const audit = screen.getByRole('region', { name: 'Items in Audit' })
    expect(within(audit).getByDisplayValue('Audit run')).toBeInTheDocument()
    // numbering follows what is shown: Notes (ungrouped) is item 1
    expect(screen.getByLabelText('Label for item 1')).toHaveValue('Notes')
    expect(screen.getByLabelText('Category for item 3')).toHaveValue('c-pay')
  })

  it('moves an item between categories with its select, and keeps moves inside a group', async () => {
    const user = userEvent.setup()
    render(<Harness categories={CATEGORIES} initial={[
      check('a', 'Audit run', 'c-audit'), check('b', 'Card batch', 'c-pay'),
    ]} />)
    await user.click(screen.getByRole('button', { name: 'Move item 2 up' })) // across a boundary: no-op
    expect(screen.getByTestId('labels')).toHaveTextContent('Audit run|Card batch')
    await user.selectOptions(screen.getByLabelText('Category for item 2'), 'c-audit')
    expect(screen.getByTestId('groups')).toHaveTextContent('c-audit|c-audit')
    await user.click(screen.getByRole('button', { name: 'Move item 2 up' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Card batch|Audit run')
    await user.selectOptions(screen.getByLabelText('Category for item 1'), '')
    expect(screen.getByTestId('groups')).toHaveTextContent('-|c-audit')
  })
})

describe('orderByCategory', () => {
  it('is a stable sort by category order, unknown categories counting as ungrouped', () => {
    const ordered = orderByCategory([
      check('1', 'p1', 'c-pay'), check('2', 'a1', 'c-audit'), check('3', 'x', 'gone'),
      check('4', 'p2', 'c-pay'), check('5', 'n', null),
    ], CATEGORIES)
    expect(ordered.map((i) => i.label)).toEqual(['x', 'n', 'a1', 'p1', 'p2'])
  })
})
