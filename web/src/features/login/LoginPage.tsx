import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useLogin, useSessionQuery } from '../../api/hooks/auth'
import { landingPath } from '../../auth/capabilities'
import { Button, Input } from '../../components/ui'

export function LoginPage() {
  const login = useLogin()
  // `isSuccess`, not just `data`: react-query keeps the last-good session payload cached
  // through a subsequent error (e.g. the cookie dying mid-session, surfaced when some other
  // request 401s and RequireAuth's refetch fails too). Trusting stale `data` alone bounced a
  // dead session straight back into the app, which RequireAuth would then bounce right back
  // out to /login — an instant redirect loop between the two.
  const { data: session, isSuccess } = useSessionQuery()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // Already signed in (or just signed in): go where the role belongs, or back where we came from.
  if (isSuccess && session && session.memberships.length > 0) {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from ?? landingPath(session.memberships[0]!.role)} replace />
  }

  return (
    <div className="grid min-h-full place-items-center bg-bg p-6">
      <form
        className="w-full max-w-sm rounded-card border border-border2 bg-surface p-6"
        onSubmit={(event) => {
          event.preventDefault()
          if (!email.trim() || !password) return
          login.mutate({ email: email.trim(), password })
        }}
      >
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded bg-accent font-mono text-sm font-bold text-accentText">
            HV
          </span>
          <div>
            <h1 className="text-base font-bold">Guest Engagement</h1>
            <p className="text-xs text-text3">Sign in to continue</p>
          </div>
        </div>

        <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-text3" htmlFor="email">
          Email
        </label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label
          className="mb-1 mt-4 block text-xs font-bold uppercase tracking-widest text-text3"
          htmlFor="password"
        >
          Password
        </label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {login.error ? (
          <p
            role="alert"
            className="mt-4 rounded border border-danger bg-dangerBg px-3 py-2 text-sm text-dangerText"
          >
            {login.error.message}
          </p>
        ) : null}

        <Button variant="primary" type="submit" loading={login.isPending} className="mt-6 w-full justify-center">
          Sign in
        </Button>
      </form>
    </div>
  )
}
