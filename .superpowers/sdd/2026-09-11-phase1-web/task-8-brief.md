### Task 8: Login, routing and the provider stack

**Files:**
- Create: `web/src/features/login/LoginPage.tsx`, `web/src/routes.tsx`, `web/src/components/ErrorBoundary.tsx`, `web/src/AppLayout.tsx`
- Modify: `web/src/App.tsx` (replace the Task 1 placeholder), `web/src/main.tsx` (add `QueryClientProvider`)
- Test: `web/src/features/login/LoginPage.test.tsx`, `web/src/routes.test.tsx`

**Interfaces:**
- Consumes: `useLogin` / `useSessionQuery` (Task 5), `landingPath` (Task 5), `RequireAuth` (Task 5), `ThemeProvider` (Task 7), `Button` / `Input` / `Spinner` / `ToastProvider` (Task 4).
- Produces: `AppRoutes` (the `<Routes>` element, exported so `routes.test.tsx` can mount it inside a `MemoryRouter`); `AppLayout` (`ThemeProvider` + `AppShell` + `<Outlet/>`); `ErrorBoundary`.

**Route table (§5.2), exactly:**

| Path | Element |
|---|---|
| `/login` | `LoginPage` — redirects to `landingPath(role)` if already authenticated |
| `/app` | `RequireAuth` → `AppLayout`; index redirects to `landingPath(role)` |
| `/app/inbox`, `/app/inbox/:id` | `InboxPage` |
| `/app/board` | `BoardPage` |
| `/app/work-orders/:id` | `WorkOrderDetailPage` |
| `/app/analytics` | `AnalyticsPage` |
| `/app/notifications` | `NotificationsPage` |
| `/app/admin/users`, `/quick-replies`, `/assets`, `/categories` | admin screens, `manage_admin` only |
| `/sim` | `SimulatorPage` — dev build only |
| `/`, anything else | redirect to `/app` |

**Placeholders are expected here.** Tasks 9-19 create the feature screens. This task stands up the table with a shared `Placeholder` component so routing can be tested now and each later task swaps in one real screen. `Placeholder` is deleted by the last feature task; it is scaffolding, not a permanent component.

**`/sim` exclusion:** `import.meta.env.DEV` is statically replaced with `false` in a production build, so the ternary folds and Rollup drops the dynamic import — the simulator's code never reaches `dist/`. Task 19 verifies this by grepping the built bundle.

**Theme lives below the session, not above it.** `ThemeProvider` needs `useSession`, so it sits in `AppLayout`. `/login` therefore renders in whatever theme `index.html` shipped (dark). That is right: there is no user yet, so there is no preference to honour.

- [ ] **Step 1: Write the failing login test**

`web/src/features/login/LoginPage.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { LoginPage } from './LoginPage'

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
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
    const [url, init] = vi.mocked(fetch).mock.calls[0]!
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
    expect(fetch).not.toHaveBeenCalled()
  })

  it('marks the password field as a password so browsers do not autofill it as text', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && npx vitest run src/features/login
```

Expected: FAIL — cannot resolve `./LoginPage`.

- [ ] **Step 3: Write `web/src/features/login/LoginPage.tsx`**

```tsx
import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useLogin, useSessionQuery } from '../../api/hooks/auth'
import { landingPath } from '../../auth/capabilities'
import { Button, Input } from '../../components/ui'

export function LoginPage() {
  const login = useLogin()
  const { data: session } = useSessionQuery()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // Already signed in (or just signed in): go where the role belongs, or back where we came from.
  if (session && session.memberships.length > 0) {
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
```

- [ ] **Step 4: Write `web/src/components/ErrorBoundary.tsx`**

```tsx
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from './ui'

type State = { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="grid h-full place-items-center bg-bg p-8 text-center">
        <div className="max-w-sm">
          <p className="text-sm font-semibold text-text">Something broke on this screen.</p>
          <p className="mt-2 text-xs text-text3">{this.state.error.message}</p>
          <Button className="mt-4" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      </div>
    )
  }
}
```

- [ ] **Step 5: Write `web/src/AppLayout.tsx` and `web/src/routes.tsx`**

`AppLayout.tsx`:

```tsx
import { Outlet } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ThemeProvider } from './theme/ThemeContext'

export function AppLayout() {
  return (
    <ThemeProvider>
      <AppShell>
        <Outlet />
      </AppShell>
    </ThemeProvider>
  )
}
```

`routes.tsx` — `Placeholder` is temporary scaffolding that later tasks replace one screen at a time:

```tsx
import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useSession } from './auth/SessionContext'
import { RequireAuth } from './auth/RequireAuth'
import { landingPath } from './auth/capabilities'
import { AppLayout } from './AppLayout'
import { EmptyState, Spinner } from './components/ui'
import { LoginPage } from './features/login/LoginPage'

/** Temporary: each feature task replaces one of these with the real screen. */
function Placeholder({ name }: { name: string }) {
  return <EmptyState title={name} hint="Not built yet." />
}

function LandingRedirect() {
  const { role } = useSession()
  return <Navigate to={landingPath(role)} replace />
}

function RequireCapability({
  capability,
  children,
}: {
  capability: 'manage_admin' | 'view_property_analytics'
  children: JSX.Element
}) {
  const { can, role } = useSession()
  if (!can(capability)) return <Navigate to={landingPath(role)} replace />
  return children
}

// Statically false in a production build, so Rollup drops the import entirely.
const SimulatorPage = import.meta.env.DEV
  ? lazy(() => import('./features/sim/SimulatorPage'))
  : null

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/app" element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<LandingRedirect />} />
          <Route path="inbox" element={<Placeholder name="Inbox" />} />
          <Route path="inbox/:id" element={<Placeholder name="Inbox" />} />
          <Route path="board" element={<Placeholder name="Board" />} />
          <Route path="work-orders/:id" element={<Placeholder name="Work order" />} />
          <Route
            path="analytics"
            element={
              <RequireCapability capability="view_property_analytics">
                <Placeholder name="Analytics" />
              </RequireCapability>
            }
          />
          <Route path="notifications" element={<Placeholder name="Alerts" />} />
          <Route
            path="admin/*"
            element={
              <RequireCapability capability="manage_admin">
                <Placeholder name="Admin" />
              </RequireCapability>
            }
          />
        </Route>
      </Route>
      {SimulatorPage ? (
        <Route
          path="/sim"
          element={
            <Suspense fallback={<Spinner />}>
              <SimulatorPage />
            </Suspense>
          }
        />
      ) : null}
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  )
}
```

- [ ] **Step 6: Replace `App.tsx` and update `main.tsx`**

`web/src/App.tsx`:

```tsx
import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './routes'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider } from './components/ui'

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  )
}
```

`web/src/main.tsx` — add the query client. `refetchOnWindowFocus` stays on: a front-desk browser sits idle for long stretches and a stale queue is the failure this product exists to prevent.

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: (failureCount, error) => {
        // Never retry a deliberate answer: auth, permission, validation, consent.
        const status = (error as { status?: number }).status ?? 0
        if (status >= 400 && status < 500) return false
        return failureCount < 2
      },
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
```

- [ ] **Step 7: Write the failing route test**

`web/src/routes.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from './api/types'
import { AppRoutes } from './routes'
import { renderWithProviders, sessionFixture } from './test/harness'

function mountAt(route: string, role: Role) {
  return renderWithProviders(<AppRoutes />, { route, session: sessionFixture({ role }) })
}

describe('AppRoutes', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends an agent from /app to the inbox', async () => {
    mountAt('/app', 'agent')
    expect(await screen.findByText('Inbox')).toBeInTheDocument()
  })

  it('sends dept_staff from /app to the board', async () => {
    mountAt('/app', 'dept_staff')
    expect(await screen.findByText('Board')).toBeInTheDocument()
  })

  it('sends a manager from /app to analytics', async () => {
    mountAt('/app', 'manager')
    expect(await screen.findByText('Analytics')).toBeInTheDocument()
  })

  it('keeps an agent out of analytics, bouncing them to their landing screen', async () => {
    mountAt('/app/analytics', 'agent')
    expect(await screen.findByText('Inbox')).toBeInTheDocument()
    expect(screen.queryByText('Analytics')).not.toBeInTheDocument()
  })

  it('keeps a manager out of admin', async () => {
    mountAt('/app/admin/users', 'manager')
    expect(await screen.findByText('Analytics')).toBeInTheDocument()
    expect(screen.queryByText('Admin')).not.toBeInTheDocument()
  })

  it('lets an admin into admin', async () => {
    mountAt('/app/admin/users', 'admin')
    expect(await screen.findByText('Admin')).toBeInTheDocument()
  })

  it('redirects an unknown path to /app', async () => {
    mountAt('/nonsense', 'agent')
    expect(await screen.findByText('Inbox')).toBeInTheDocument()
  })

  it('sends an unauthenticated visitor to /login', async () => {
    renderWithProviders(<AppRoutes />, { route: '/app/inbox' })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 8: Run the tests**

```bash
cd web && npm test
```

Expected: PASS — 6 login tests and 8 route tests. `AppShell` does not exist yet, so `AppLayout` will fail to import. **Implementer: create `web/src/components/AppShell.tsx` as a one-line pass-through for now** — `export function AppShell({ children }: { children: ReactNode }) { return <>{children}</> }` — and let Task 9 replace it wholesale. Note this in your task report so the reviewer knows the stub is deliberate and scoped.

- [ ] **Step 9: Verify against the real server**

Start the server (`.\start.bat` from the repo root, or `npm run server`) and `npm run web`, then:
- `http://localhost:5173/app/inbox` → redirected to `/login`
- sign in as `ava@hvh.test` / `Password123!` → lands on `/app/inbox` showing the Inbox placeholder
- sign in as `eli@hvh.test` → lands on `/app/board`
- sign in as `morgan@hvh.test` → lands on `/app/analytics`
- as Ava, visit `/app/admin/users` by hand → bounced back to `/app/inbox`

- [ ] **Step 10: Commit**

```bash
git add web/src/App.tsx web/src/main.tsx web/src/routes.tsx web/src/AppLayout.tsx \
        web/src/routes.test.tsx web/src/features/login web/src/components
git commit -m "feat(web): login, route table with role landings and capability guards"
```

---

