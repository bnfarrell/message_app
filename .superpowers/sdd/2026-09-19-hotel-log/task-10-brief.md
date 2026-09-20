## Task 10: MentionInput

**Files:**
- Create: `web/src/features/log/MentionInput.tsx`, `web/src/features/log/MentionInput.test.tsx`

**Interfaces:**
- Produces:
  ```ts
  export type MentionRef = { type: 'user' | 'department'; id: string }
  export function MentionInput(props: {
    value: string
    mentions: MentionRef[]
    options: LogMentionableOut[]
    onChange: (value: string, mentions: MentionRef[]) => void
    placeholder?: string
    id?: string
  }): JSX.Element
  export const TOKEN_RE: RegExp
  export function tokenFor(option: LogMentionableOut): string
  ```
- The token format is `@[Display Name](type:id)`, matching spec §6.1.

- [ ] **Step 1: Write the failing test**

Create `web/src/features/log/MentionInput.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MentionInput, tokenFor } from './MentionInput'
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
    expect(body).toBe(tokenFor(OPTIONS[1]))
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
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npm test -- MentionInput`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `web/src/features/log/MentionInput.tsx`. Requirements the test pins down, and which the implementer must satisfy exactly:

- A `<textarea role="textbox">` whose value is the controlled `value` prop.
- Typing `@` followed by word characters at the caret opens a `role="listbox"` of `role="option"` entries, filtered case-insensitively on `displayName` against the text after the `@`.
- Clicking an option replaces the `@query` fragment with `tokenFor(option)` and calls `onChange(nextValue, [...mentions, { type, id }])`, de-duplicating by `type+id`.
- No matches means no listbox in the DOM at all (not a hidden one).
- `tokenFor({type,id,displayName})` returns `` `@[${displayName}](${type}:${id})` ``.
- `TOKEN_RE` is `/@\[([^\]]+)\]\((user|department):([0-9a-f-]{36})\)/g` — exported so `LogEntryCard` renders with the same grammar the composer writes.
- Keyboard: ArrowDown/ArrowUp move the active option, Enter selects it, Escape closes the menu. Give the active option `aria-selected`.
- Follow the styling idiom of `web/src/features/inbox/QuickReplyPalette.tsx`, which is this codebase's existing filtered-popup component — read it before writing.

- [ ] **Step 4: Run to verify it passes**

Run: `cd web && npm test -- MentionInput`
Expected: PASS, 3 tests.

- [ ] **Step 5: Lint and commit**

```bash
cd web && npm run lint
git add web/src/features/log/MentionInput.tsx web/src/features/log/MentionInput.test.tsx
git commit -m "feat(web): mention picker that records ids rather than names"
```

---

