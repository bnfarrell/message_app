import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { LoginPage } from './LoginPage'

// LoginPage calls useSessionQuery() on mount (to redirect an already-authenticated visitor),
// so /api/auth/me is always fetched before any login POST. A single mockResolvedValue would
// (a) hand that mount-time check the same "successful login" body, redirecting away from the
// form before the test can submit it, and (b) reuse one Response object across both calls --
// a Response body can only be read once, so the second .json() throws and the real error
// message is lost to the generic fallback. Answer /api/auth/login with the given response and
// everything else (the mount-time check) with "not signed in", via a fresh Response each time.
function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockImplementation((input) => {
    const isLogin = String(input) === '/api/auth/login'
    const [respStatus, respBody] = isLogin
      ? [status, body]
      : [401, { error: { code: 'UNAUTHORIZED', message: 'Not signed in' } }]
    return Promise.resolve(
      new Response(JSON.stringify(respBody), {
        status: respStatus,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('asks for an email and a password', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('posts the credentials to /api/auth/login', async () => {
    respond(200, sessionFixture())
    renderWithProviders(<LoginPage />)
    await userEvent.type(screen.getByLabelText('Email'), 'ava@hvh.test')
    await userEvent.type(screen.getByLabelText('Password'), 'Password123!')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(fetch).toHaveBeenCalled())
    // Not calls[0]: the mount-time /api/auth/me check is called first, ahead of the login POST.
    const call = vi.mocked(fetch).mock.calls.find(([input]) => String(input) === '/api/auth/login')
    expect(call, 'the login request was not sent').toBeDefined()
    const [url, init] = call!
    expect(url).toBe('/api/auth/login')
    expect(init).toMatchObject({ method: 'POST' })
    expect(JSON.parse(String(init!.body))).toEqual({
      email: 'ava@hvh.test',
      password: 'Password123!',
    })
  })

  it('shows the server message when the credentials are wrong', async () => {
    respond(401, { error: { code: 'UNAUTHORIZED', message: 'Email or password is incorrect' } })
    renderWithProviders(<LoginPage />)
    await userEvent.type(screen.getByLabelText('Email'), 'ava@hvh.test')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect')
  })

  it('surfaces the rate-limit message rather than a generic failure', async () => {
    respond(429, { error: { code: 'RATE_LIMITED', message: 'Too many attempts. Try again soon.' } })
    renderWithProviders(<LoginPage />)
    await userEvent.type(screen.getByLabelText('Email'), 'ava@hvh.test')
    await userEvent.type(screen.getByLabelText('Password'), 'x')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Too many attempts')
  })

  it('does not submit an empty form', async () => {
    renderWithProviders(<LoginPage />)
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    // Not "fetch was never called": mounting always fires the /api/auth/me session check.
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input) === '/api/auth/login')).toBe(
      false,
    )
  })

  it('marks the password field as a password so browsers do not autofill it as text', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })
})
