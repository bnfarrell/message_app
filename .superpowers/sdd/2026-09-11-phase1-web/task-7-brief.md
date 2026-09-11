### Task 7: Theme — dark default, light toggle, persisted per user

**Files:**
- Create: `web/src/theme/ThemeContext.tsx`
- Test: `web/src/theme/ThemeContext.test.tsx`
- Modify: `web/src/api/hooks/auth.ts` (add `useSetPrefs`)
- Modify: `web/src/test/harness.tsx` — add `notificationPrefs: opts.prefs ?? {}` to the `user` object in `sessionFixture`, and `prefs?: Record<string, unknown>` to its options type. Task 6 added the field to `UserOut`; the fixture must carry it or every theme test has to reach in and assign it.

**Interfaces:**
- Consumes: `useSession` (Task 5), `api`/`qk` (Task 3), `PATCH /api/auth/prefs` (Task 6).
- Produces: `ThemeProvider`; `useTheme(): { theme: 'dark' | 'light' | 'system'; resolved: 'dark' | 'light'; setTheme: (t: 'dark' | 'light' | 'system') => void }`; `useSetPrefs(): UseMutationResult<SessionOut, ApiError, { theme: 'dark' | 'light' | 'system' }>`.

**Behaviour from §5.0:** dark is the default. The stored value is one of three: `dark`, `light`, or `system` — and `system` resolves through `prefers-color-scheme`. The resolved value is written to `document.documentElement.dataset.theme`, which is what `index.css` keys on. A user with no stored preference gets `system`.

**Why the DOM attribute and not a React class:** `index.html` ships `data-theme="dark"` so the very first paint is already dark, before React mounts. The provider only corrects it.

- [ ] **Step 1: Write the failing test**

`web/src/theme/ThemeContext.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { qk } from '../api/queryKeys'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { ThemeProvider, useTheme } from './ThemeContext'

function Probe() {
  const { theme, resolved, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolved}</span>
      <button onClick={() => setTheme('light')}>light</button>
      <button onClick={() => setTheme('system')}>system</button>
    </div>
  )
}

function prefersDark(dark: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: dark && query.includes('dark'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    })),
  )
}

function withTheme(session = sessionFixture()) {
  return renderWithProviders(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
    { session },
  )
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-theme')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('defaults to system when the user has no stored preference', async () => {
    prefersDark(true)
    withTheme()
    await waitFor(() => expect(screen.getByTestId('theme')).toHaveTextContent('system'))
  })

  it('resolves system to dark when the device prefers dark', async () => {
    prefersDark(true)
    withTheme()
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark')
  })

  it('resolves system to light when the device prefers light', async () => {
    prefersDark(false)
    withTheme()
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
  })

  it('uses the stored preference over the device setting', async () => {
    prefersDark(true)
    const session = sessionFixture()
    session.user.notificationPrefs = { theme: 'light' }
    withTheme(session)
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
  })

  it('applies a change immediately and persists it to the server', async () => {
    prefersDark(true)
    withTheme()
    await userEvent.click(screen.getByRole('button', { name: 'light' }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url) === '/api/auth/prefs')
    expect(call, 'the theme change was not sent to the server').toBeDefined()
    expect(call![1]).toMatchObject({ method: 'PATCH' })
    expect(call![1]!.body).toBe('{"theme":"light"}')
  })

  it('keeps the chosen theme on screen even if the save fails', async () => {
    prefersDark(true)
    vi.mocked(fetch).mockRejectedValue(new TypeError('offline'))
    withTheme()
    await userEvent.click(screen.getByRole('button', { name: 'light' }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
  })

  it('ignores a stored value that is not a theme', async () => {
    prefersDark(true)
    const session = sessionFixture()
    session.user.notificationPrefs = { theme: 'sepia' }
    withTheme(session)
    await waitFor(() => expect(screen.getByTestId('theme')).toHaveTextContent('system'))
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && npx vitest run src/theme
```

Expected: FAIL — cannot resolve `./ThemeContext`.

- [ ] **Step 3: Add `useSetPrefs` to `web/src/api/hooks/auth.ts`**

```ts
export function useSetPrefs() {
  const client = useQueryClient()
  return useMutation<SessionOut, ApiError, { theme: 'dark' | 'light' | 'system' }>({
    mutationFn: (body) => api<SessionOut>('/api/auth/prefs', { method: 'PATCH', json: body }),
    onSuccess: (session) => {
      client.setQueryData(qk.session, session)
    },
  })
}
```

- [ ] **Step 4: Write `web/src/theme/ThemeContext.tsx`**

```tsx
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useSetPrefs } from '../api/hooks/auth'
import { useSession } from '../auth/SessionContext'

export type ThemeChoice = 'dark' | 'light' | 'system'

const CHOICES: ThemeChoice[] = ['dark', 'light', 'system']

type ThemeValue = {
  theme: ThemeChoice
  resolved: 'dark' | 'light'
  setTheme: (theme: ThemeChoice) => void
}

const ThemeContext = createContext<ThemeValue | null>(null)

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside a ThemeProvider')
  return value
}

function storedChoice(prefs: Record<string, unknown> | undefined): ThemeChoice {
  const raw = prefs?.['theme']
  return CHOICES.includes(raw as ThemeChoice) ? (raw as ThemeChoice) : 'system'
}

function devicePrefersDark(): boolean {
  // Absent in older jsdom and in some embedded webviews; dark is the product default.
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user } = useSession()
  const setPrefs = useSetPrefs()
  const [theme, setLocal] = useState<ThemeChoice>(() =>
    storedChoice(user.notificationPrefs as Record<string, unknown> | undefined),
  )
  const resolved: 'dark' | 'light' =
    theme === 'system' ? (devicePrefersDark() ? 'dark' : 'light') : theme

  useEffect(() => {
    document.documentElement.dataset.theme = resolved
  }, [resolved])

  const setTheme = useCallback(
    (next: ThemeChoice) => {
      // Local first: the toggle must feel instant, and a failed save should not revert
      // the user's choice for this session. The next load falls back to the server value.
      setLocal(next)
      setPrefs.mutate({ theme: next })
    },
    [setPrefs],
  )

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme }}>{children}</ThemeContext.Provider>
  )
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 7 theme tests.

Note `setPrefs.mutate` rejects unhandled when the request fails; the test `keeps the chosen theme on screen even if the save fails` covers it. React Query swallows mutation errors into state, so no unhandled rejection escapes.

- [ ] **Step 6: Commit**

```bash
git add web/src/theme web/src/api/hooks/auth.ts
git commit -m "feat(web): theme provider with dark default, system fallback and server persistence"
```

---

