import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../auth/SessionContext'
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
    <SessionProvider>
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    </SessionProvider>,
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
