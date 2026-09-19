import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MentionInput, tokenFor, type MentionRef } from './MentionInput'
import type { LogMentionableOut } from '../../api/types'

const OPTIONS: LogMentionableOut[] = [
  { type: 'user', id: 'u1', displayName: 'Ana Marquez', subtitle: 'agent' },
  { type: 'user', id: 'u2', displayName: 'Ana Maria-Bonilla', subtitle: 'agent' },
  { type: 'department', id: 'd1', displayName: 'Front Desk', subtitle: 'Department' },
]

describe('MentionInput', () => {
  it('records the id of the option picked, not the typed name', async () => {
    const onChange = vi.fn()
    render(<MentionInput value="" mentions={[]} options={OPTIONS} onChange={onChange} />)
    await userEvent.type(screen.getByRole('textbox'), '@Ana')
    // Both Anas are offered — the ambiguity the regex resolver could not handle.
    expect(screen.getAllByRole('option')).toHaveLength(2)
    await userEvent.click(screen.getByRole('option', { name: /Ana Maria-Bonilla/ }))
    const [body, mentions] = onChange.mock.calls.at(-1)!
    expect(body).toBe(tokenFor(OPTIONS[1]!))
    expect(mentions).toEqual([{ type: 'user', id: 'u2' }])
  })

  it('offers departments too', async () => {
    const onChange = vi.fn()
    render(<MentionInput value="" mentions={[]} options={OPTIONS} onChange={onChange} />)
    await userEvent.type(screen.getByRole('textbox'), '@Front')
    await userEvent.click(screen.getByRole('option', { name: /Front Desk/ }))
    const [, mentions] = onChange.mock.calls.at(-1)!
    expect(mentions).toEqual([{ type: 'department', id: 'd1' }])
  })

  it('closes the menu when no option matches', async () => {
    render(<MentionInput value="" mentions={[]} options={OPTIONS} onChange={vi.fn()} />)
    await userEvent.type(screen.getByRole('textbox'), '@zzzz')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('moves the active option with the arrow keys and picks it with Enter', async () => {
    const onChange = vi.fn()
    render(<MentionInput value="" mentions={[]} options={OPTIONS} onChange={onChange} />)
    await userEvent.type(screen.getByRole('textbox'), '@Ana')
    const [first, second] = screen.getAllByRole('option')
    // Freshly opened: the first option is active, not the second.
    expect(first).toHaveAttribute('aria-selected', 'true')
    expect(second).toHaveAttribute('aria-selected', 'false')

    await userEvent.keyboard('{ArrowDown}')
    expect(first).toHaveAttribute('aria-selected', 'false')
    expect(second).toHaveAttribute('aria-selected', 'true')

    await userEvent.keyboard('{Enter}')
    const [, mentions] = onChange.mock.calls.at(-1)!
    // Enter picked the arrowed-to option (Ana Maria-Bonilla, index 1), not the first.
    expect(mentions).toEqual([{ type: 'user', id: 'u2' }])
  })

  it('closes the menu on Escape without picking anything', async () => {
    const onChange = vi.fn()
    render(<MentionInput value="" mentions={[]} options={OPTIONS} onChange={onChange} />)
    await userEvent.type(screen.getByRole('textbox'), '@Ana')
    expect(screen.getAllByRole('option')).toHaveLength(2)

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    // Escape must not have fired a pick — only the typing calls reached onChange.
    expect(onChange).not.toHaveBeenCalledWith(expect.anything(), expect.arrayContaining([expect.anything()]))
  })

  it('de-dupes a mention picked twice into a single entry', async () => {
    const onChange = vi.fn()
    function Harness() {
      const [value, setValue] = useState('')
      const [mentions, setMentions] = useState<MentionRef[]>([])
      return (
        <MentionInput
          value={value}
          mentions={mentions}
          options={OPTIONS}
          onChange={(nextValue, nextMentions) => {
            onChange(nextValue, nextMentions)
            setValue(nextValue)
            setMentions(nextMentions)
          }}
        />
      )
    }
    render(<Harness />)
    const textbox = screen.getByRole('textbox')

    await userEvent.type(textbox, '@Ana')
    await userEvent.click(screen.getByRole('option', { name: /^Ana Marquez/ }))

    await userEvent.type(textbox, ' @Ana')
    await userEvent.click(screen.getByRole('option', { name: /^Ana Marquez/ }))

    // Same person mentioned twice in the body, but only one mention record.
    expect(textbox).toHaveValue(`${tokenFor(OPTIONS[0]!)} ${tokenFor(OPTIONS[0]!)}`)
    const [, mentions] = onChange.mock.calls.at(-1)!
    expect(mentions).toEqual([{ type: 'user', id: 'u1' }])
  })
})
