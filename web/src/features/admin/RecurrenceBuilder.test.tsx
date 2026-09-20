import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { RecurrenceBuilder, composeSimpleRule, parseSimpleRule } from './RecurrenceBuilder'

/** The builder is a controlled input; a bare mock as `onChange` would leave `value` frozen and
 *  every keystroke would be typed against the stale string. This holds the state like the
 *  admin screen does and records each change. */
function Harness({ initial, onChange }: { initial: string; onChange: (rrule: string) => void }) {
  const [value, setValue] = useState(initial)
  return (
    <RecurrenceBuilder
      value={value}
      onChange={(next) => {
        setValue(next)
        onChange(next)
      }}
    />
  )
}

describe('recurrence rules', () => {
  it('round-trips the simple shape', () => {
    expect(composeSimpleRule('MONTHLY', 3)).toBe('FREQ=MONTHLY;INTERVAL=3')
    expect(composeSimpleRule('WEEKLY', 1)).toBe('FREQ=WEEKLY')
    expect(parseSimpleRule('FREQ=MONTHLY;INTERVAL=3')).toEqual({ freq: 'MONTHLY', interval: 3 })
    expect(parseSimpleRule('FREQ=DAILY')).toEqual({ freq: 'DAILY', interval: 1 })
    expect(parseSimpleRule('FREQ=WEEKLY;BYDAY=MO,WE')).toBeNull()
    expect(parseSimpleRule('')).toEqual({ freq: 'MONTHLY', interval: 1 })
  })

  it('composes from the controls and hands off to the raw field for anything else', async () => {
    const onChange = vi.fn()
    render(<Harness initial="FREQ=MONTHLY;INTERVAL=3" onChange={onChange} />)
    expect(screen.getByLabelText('Every')).toHaveValue(3)
    await userEvent.selectOptions(screen.getByLabelText('Period'), 'YEARLY')
    expect(onChange).toHaveBeenLastCalledWith('FREQ=YEARLY;INTERVAL=3')

    await userEvent.click(screen.getByRole('button', { name: 'Advanced' }))
    await userEvent.clear(screen.getByLabelText('RRULE'))
    await userEvent.type(screen.getByLabelText('RRULE'), 'FREQ=WEEKLY;BYDAY=MO')
    expect(onChange).toHaveBeenLastCalledWith('FREQ=WEEKLY;BYDAY=MO')
  })

  it('disables the controls while the rule is beyond what they can express', () => {
    render(<RecurrenceBuilder value="FREQ=WEEKLY;BYDAY=MO" onChange={() => {}} />)
    expect(screen.getByLabelText('Every')).toBeDisabled()
    expect(screen.getByLabelText('RRULE')).toHaveValue('FREQ=WEEKLY;BYDAY=MO')
  })
})
