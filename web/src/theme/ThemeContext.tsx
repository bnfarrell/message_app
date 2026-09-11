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
