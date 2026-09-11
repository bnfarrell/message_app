### Task 5: Session, capabilities, active property and route guarding

**Files:**
- Create: `web/src/api/hooks/auth.ts`, `web/src/auth/capabilities.ts`, `web/src/auth/SessionContext.tsx`, `web/src/auth/RequireAuth.tsx`
- Create: `web/src/test/harness.tsx` (shared test wrapper — every later task's component test uses it)
- Test: `web/src/auth/capabilities.test.ts`, `web/src/auth/SessionContext.test.tsx`

**Interfaces:**
- Consumes: `api`, `ApiError`, `onUnauthorized` (Task 3), `qk` (Task 3), types (Task 2), `Spinner` (Task 4).
- Produces:
  - `capabilities.ts`: `type Capability = 'view_all_conversations' | 'reply' | 'assign' | 'add_note' | 'archive' | 'create_work_order' | 'close_work_order' | 'view_property_analytics' | 'view_own_stats' | 'manage_admin' | 'export'`; `hasCapability(role: Role, capability: Capability): boolean`; `landingPath(role: Role): string`
  - `useLogin(): UseMutationResult<SessionOut, ApiError, LoginRequest>`, `useLogout(): UseMutationResult<void, ApiError, void>`
  - `SessionProvider` and `useSession(): Session` where

    ```ts
    type Session = {
      user: UserOut
      memberships: MembershipOut[]
      membership: MembershipOut   // the active property's membership
      propertyId: string
      role: Role
      can: (capability: Capability) => boolean
      setPropertyId: (id: string) => void
      logout: () => void
    }
    ```
  - `useSessionQuery()` — the raw query, for the one caller (`RequireAuth`) that needs `isPending` / `error`
  - `RequireAuth` — a `<Outlet/>` guard
  - `harness.tsx`: `renderWithProviders(ui: ReactNode, opts?: { session?: SessionOut; route?: string; client?: QueryClient }): RenderResult & { client: QueryClient }`

**Why `useSession()` throws outside a provider:** every screen below `RequireAuth` is guaranteed a session, so making `user` optional would push a `?.` into ~30 components to satisfy a case that cannot happen. `RequireAuth` is the single place that handles "not logged in yet".

**Capability values are copied from `server/app/auth/permissions.py`.** They must match exactly; a client that shows a button the server will 403 is worse than one that hides it.

- [ ] **Step 1: Write the failing capability test**

`web/src/auth/capabilities.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { Role } from '../api/types'
import { hasCapability, landingPath } from './capabilities'

describe('hasCapability', () => {
  it('lets agents reply but not close work orders', () => {
    expect(hasCapability('agent', 'reply')).toBe(true)
    expect(hasCapability('agent', 'close_work_order')).toBe(false)
  })

  it('lets dept_staff close work orders but not archive conversations', () => {
    expect(hasCapability('dept_staff', 'close_work_order')).toBe(true)
    expect(hasCapability('dept_staff', 'archive')).toBe(false)
  })

  it('keeps dept_staff out of the property-wide conversation list', () => {
    expect(hasCapability('dept_staff', 'view_all_conversations')).toBe(false)
    expect(hasCapability('agent', 'view_all_conversations')).toBe(true)
  })

  it('gives corporate analytics but not reply or admin-side writes', () => {
    expect(hasCapability('corporate', 'view_property_analytics')).toBe(true)
    expect(hasCapability('corporate', 'reply')).toBe(false)
    expect(hasCapability('corporate', 'manage_admin')).toBe(true)
  })

  it('restricts admin screens to admin and corporate', () => {
    const allowed: Role[] = ['admin', 'corporate']
    const denied: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager']
    for (const r of allowed) expect(hasCapability(r, 'manage_admin'), r).toBe(true)
    for (const r of denied) expect(hasCapability(r, 'manage_admin'), r).toBe(false)
  })

  it('lets every staff role add a note', () => {
    const all: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']
    for (const r of all) expect(hasCapability(r, 'add_note'), r).toBe(true)
  })
})

describe('landingPath', () => {
  it('sends each role where §5.2 says', () => {
    expect(landingPath('agent')).toBe('/app/inbox')
    expect(landingPath('dept_staff')).toBe('/app/board?mine=1')
    expect(landingPath('supervisor')).toBe('/app/board?mine=1')
    expect(landingPath('manager')).toBe('/app/analytics')
    expect(landingPath('admin')).toBe('/app/analytics')
    expect(landingPath('corporate')).toBe('/app/analytics')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && npx vitest run src/auth/capabilities.test.ts
```

Expected: FAIL — cannot resolve `./capabilities`.

- [ ] **Step 3: Write `web/src/auth/capabilities.ts`**

```ts
import type { Role } from '../api/types'

export type Capability =
  | 'view_all_conversations'
  | 'reply'
  | 'assign'
  | 'add_note'
  | 'archive'
  | 'create_work_order'
  | 'close_work_order'
  | 'view_property_analytics'
  | 'view_own_stats'
  | 'manage_admin'
  | 'export'

const STAFF: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']

/** Mirrors server/app/auth/permissions.py CAPABILITIES. Keep the two in step. */
const CAPABILITIES: Record<Capability, Role[]> = {
  view_all_conversations: ['agent', 'supervisor', 'manager', 'admin', 'corporate'],
  reply: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  assign: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  add_note: STAFF,
  archive: ['agent', 'supervisor', 'manager', 'admin'],
  create_work_order: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  close_work_order: ['dept_staff', 'supervisor', 'manager', 'admin'],
  view_property_analytics: ['supervisor', 'manager', 'admin', 'corporate'],
  view_own_stats: ['agent', 'dept_staff'],
  manage_admin: ['admin', 'corporate'],
  export: ['manager', 'admin', 'corporate'],
}

export function hasCapability(role: Role, capability: Capability): boolean {
  return CAPABILITIES[capability].includes(role)
}

/** §5.2: /app redirects here. */
export function landingPath(role: Role): string {
  switch (role) {
    case 'agent':
      return '/app/inbox'
    case 'dept_staff':
    case 'supervisor':
      return '/app/board?mine=1'
    case 'manager':
    case 'admin':
    case 'corporate':
      return '/app/analytics'
  }
}
```

- [ ] **Step 4: Write `web/src/api/hooks/auth.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../client'
import { qk } from '../queryKeys'
import type { LoginRequest, SessionOut } from '../types'

export function useSessionQuery() {
  return useQuery<SessionOut, ApiError>({
    queryKey: qk.session,
    queryFn: () => api<SessionOut>('/api/auth/me'),
    // A 401 here is the answer ("not logged in"), not a transient failure worth retrying.
    retry: false,
    staleTime: Infinity,
  })
}

export function useLogin() {
  const client = useQueryClient()
  return useMutation<SessionOut, ApiError, LoginRequest>({
    mutationFn: (body) => api<SessionOut>('/api/auth/login', { method: 'POST', json: body }),
    onSuccess: (session) => {
      client.setQueryData(qk.session, session)
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () => api<void>('/api/auth/logout', { method: 'POST' }),
    // Clear unconditionally: a failed logout must not leave another user's cache on screen.
    onSettled: () => {
      client.clear()
    },
  })
}
```

- [ ] **Step 5: Write the failing session test**

`web/src/auth/SessionContext.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, sessionFixture } from '../test/harness'
import { SessionProvider, useSession } from './SessionContext'

function Probe() {
  const { user, role, propertyId, can, setPropertyId } = useSession()
  return (
    <div>
      <span data-testid="who">{user.firstName}</span>
      <span data-testid="role">{role}</span>
      <span data-testid="property">{propertyId}</span>
      <span data-testid="can-archive">{String(can('archive'))}</span>
      <button onClick={() => setPropertyId('prop-b')}>switch</button>
    </div>
  )
}

describe('SessionProvider', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('exposes the user, the active membership role and its capabilities', async () => {
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    await waitFor(() => expect(screen.getByTestId('who')).toHaveTextContent('Ava'))
    expect(screen.getByTestId('role')).toHaveTextContent('agent')
    expect(screen.getByTestId('property')).toHaveTextContent('prop-a')
    expect(screen.getByTestId('can-archive')).toHaveTextContent('true')
  })

  it('defaults to the first membership when nothing is stored', async () => {
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent', withSecondProperty: true }) },
    )
    await waitFor(() => expect(screen.getByTestId('property')).toHaveTextContent('prop-a'))
  })

  it('restores a stored active property when it is still a membership', async () => {
    localStorage.setItem('activePropertyId', 'prop-b')
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent', withSecondProperty: true }) },
    )
    await waitFor(() => expect(screen.getByTestId('property')).toHaveTextContent('prop-b'))
  })

  it('ignores a stored property the user no longer has access to', async () => {
    localStorage.setItem('activePropertyId', 'prop-gone')
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    await waitFor(() => expect(screen.getByTestId('property')).toHaveTextContent('prop-a'))
  })

  it('takes the role from the active property, not the first one', async () => {
    localStorage.setItem('activePropertyId', 'prop-b')
    renderWithProviders(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent', withSecondProperty: true, secondRole: 'admin' }) },
    )
    await waitFor(() => expect(screen.getByTestId('role')).toHaveTextContent('admin'))
  })

  it('throws when used outside the provider, so a missing provider fails loudly', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderWithProviders(<Probe />)).toThrow(/SessionProvider/)
    quiet.mockRestore()
  })
})
```

`web/src/test/harness.tsx` — the shared wrapper. It seeds the session cache directly instead of mocking `/api/auth/me`, so component tests never depend on fetch timing:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type RenderResult, render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { qk } from '../api/queryKeys'
import type { MembershipOut, Role, SessionOut } from '../api/types'

export function sessionFixture(opts: {
  role?: Role
  withSecondProperty?: boolean
  secondRole?: Role
  departmentId?: string | null
} = {}): SessionOut {
  const memberships: MembershipOut[] = [
    {
      propertyId: 'prop-a',
      propertyName: 'Harbourview Hotel',
      propertyCode: 'HVH',
      role: opts.role ?? 'agent',
      departmentId: opts.departmentId ?? null,
    },
  ]
  if (opts.withSecondProperty) {
    memberships.push({
      propertyId: 'prop-b',
      propertyName: 'Lakeside Inn',
      propertyCode: 'LSI',
      role: opts.secondRole ?? opts.role ?? 'agent',
      departmentId: null,
    })
  }
  return {
    user: {
      id: 'u-ava',
      email: 'ava@hvh.test',
      firstName: 'Ava',
      lastName: 'Nolan',
      locale: 'en',
      avatarUrl: null,
    },
    memberships,
  }
}

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
}

export function renderWithProviders(
  ui: ReactNode,
  opts: { session?: SessionOut; route?: string; client?: QueryClient } = {},
): RenderResult & { client: QueryClient } {
  const client = opts.client ?? testQueryClient()
  if (opts.session) client.setQueryData(qk.session, opts.session)
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[opts.route ?? '/']}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, client }
}
```

- [ ] **Step 6: Run it to verify it fails**

```bash
cd web && npx vitest run src/auth/SessionContext.test.tsx
```

Expected: FAIL — cannot resolve `./SessionContext`.

- [ ] **Step 7: Write `web/src/auth/SessionContext.tsx`**

```tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useLogout, useSessionQuery } from '../api/hooks/auth'
import type { MembershipOut, Role, UserOut } from '../api/types'
import { hasCapability, type Capability } from './capabilities'

const STORAGE_KEY = 'activePropertyId'

export type Session = {
  user: UserOut
  memberships: MembershipOut[]
  membership: MembershipOut
  propertyId: string
  role: Role
  can: (capability: Capability) => boolean
  setPropertyId: (id: string) => void
  logout: () => void
}

const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside a SessionProvider')
  return value
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const { data } = useSessionQuery()
  const logoutMutation = useLogout()
  const [stored, setStored] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY)
    } catch {
      return null // private mode / blocked storage: fall back to the first membership
    }
  })

  const setPropertyId = useCallback((id: string) => {
    setStored(id)
    try {
      localStorage.setItem(STORAGE_KEY, id)
    } catch {
      /* not fatal — the choice just will not survive a reload */
    }
  }, [])

  const value = useMemo<Session | null>(() => {
    if (!data || data.memberships.length === 0) return null
    const membership =
      data.memberships.find((m) => m.propertyId === stored) ?? data.memberships[0]!
    return {
      user: data.user,
      memberships: data.memberships,
      membership,
      propertyId: membership.propertyId,
      role: membership.role,
      can: (capability) => hasCapability(membership.role, capability),
      setPropertyId,
      logout: () => logoutMutation.mutate(),
    }
  }, [data, stored, setPropertyId, logoutMutation])

  if (!value) return null
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
```

- [ ] **Step 8: Write `web/src/auth/RequireAuth.tsx`**

```tsx
import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSessionQuery } from '../api/hooks/auth'
import { onUnauthorized } from '../api/client'
import { Spinner } from '../components/ui/Spinner'
import { SessionProvider } from './SessionContext'

export function RequireAuth() {
  const { data, isPending, error, refetch } = useSessionQuery()
  const location = useLocation()

  // Any 401 from any request means the cookie died mid-session; refetching /api/auth/me
  // flips this guard to the redirect below instead of leaving a half-dead screen up.
  useEffect(() => {
    onUnauthorized(() => void refetch())
    return () => onUnauthorized(null)
  }, [refetch])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center bg-bg">
        <Spinner />
      </div>
    )
  }

  if (error || !data) {
    const from = `${location.pathname}${location.search}`
    return <Navigate to="/login" replace state={{ from }} />
  }

  if (data.memberships.length === 0) {
    return (
      <div className="grid h-full place-items-center bg-bg p-8 text-center">
        <p className="max-w-sm text-text2">
          Your account has no property access yet. Ask an administrator to add you to a property.
        </p>
      </div>
    )
  }

  return (
    <SessionProvider>
      <Outlet />
    </SessionProvider>
  )
}
```

- [ ] **Step 9: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 6 capability tests, 1 landing test and 6 session tests, on top of Tasks 1-4's.

- [ ] **Step 10: Commit**

```bash
git add web/src/auth web/src/api/hooks/auth.ts web/src/test/harness.tsx
git commit -m "feat(web): session context, capability map mirroring the server, and route guard"
```

---

