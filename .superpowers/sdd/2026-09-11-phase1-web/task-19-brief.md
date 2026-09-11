### Task 19: Admin CRUD

**Files:**
- Create: `web/src/features/admin/AdminPage.tsx`, `AdminTable.tsx`, `EditPanel.tsx`, `UsersAdmin.tsx`, `QuickRepliesAdmin.tsx`, `AssetsAdmin.tsx`, `CategoriesAdmin.tsx`
- Modify: `web/src/api/hooks/content.ts` (add the write mutations), `web/src/api/hooks/users.ts` (add staff writes), `web/src/routes.tsx`
- Test: `web/src/features/admin/QuickRepliesAdmin.test.tsx`, `UsersAdmin.test.tsx`, `AdminPage.test.tsx`

**Interfaces:**
- Consumes: `useQuickReplies` / `useAssets` / `useCategories` (Task 14), `useStaff` / `useDepartments` (Task 12), primitives (Task 4).
- Produces:
  - `content.ts` additions: `useCreateQuickReply`, `usePatchQuickReply`, `useDeleteQuickReply`, `useCreateAsset`, `usePatchAsset`, `useDeleteAsset`, `useCreateCategory`, `usePatchCategory`, `useDeleteCategory`
  - `users.ts` additions: `useCreateStaff` (`POST users` with `CreateStaffRequest`), `usePatchStaff` (`PATCH users/<id>` with `StaffPatch`), `useDeleteStaff`
  - `AdminTable<T>({ columns, rows, selectedId, onSelect })`, `EditPanel({ title, subtitle, children, onSave, onDelete, onCancel, saving, error })`, `AdminPage`

**One pattern, four screens** (mockup `Admin.dc.html`): a sub-nav of admin sections down the left of the content area (`.sub`, 40 px, active row `bg-surface2` with `inset 3px 0 0 var(--accent)`), a table in the middle, and an edit panel on the right that appears when a row is selected or **New** is clicked. §5.0 says the other admin screens reuse the quick-replies table + edit-panel pattern, so `AdminTable` and `EditPanel` are built once and the four screens supply columns and fields.

**Phase 2 sections are listed and greyed**, exactly as the mockup shows: `Departments`, `Property settings`, `Automations`, `Blocked numbers`, `Integrations` render as disabled rows under the caption "Greyed items arrive in Phase 2". They are not links. Showing them is deliberate — it tells an admin the shape of the product rather than implying these things do not exist.

**Live sections and their fields:**

| Section | Route | Columns | Editable fields |
|---|---|---|---|
| Users & roles | `/app/admin/users` | Name · Email · Role · Department | role (`Role` enum), department; **create** also takes first name, last name, email, optional password and phone |
| Quick replies | `/app/admin/quick-replies` | Shortcut (mono) · Title · Body (truncated) · Dept · Uses · Active | shortcut, title, body, department, category, locale, active |
| Digital assets | `/app/admin/assets` | Name · Type · Short code (mono) · Sends · Active | name, type, url, description, category, department, validFrom, validUntil, active |
| Resolution categories | `/app/admin/categories` | Name (indented by depth) · Parent · Active | name, parent, active |

**Delete is a confirm, not a dialog chain.** Each edit panel's **Delete** asks once inline ("Delete this? This cannot be undone." with Confirm/Cancel in place of the button) rather than opening a modal over a panel. The server soft-handles what it can; the client does not pretend otherwise.

**The whole route is already gated** on `manage_admin` by Task 8's `RequireCapability`, so no per-section capability checks are needed here.

**A quick reply's `usageCount` is read-only** — it comes from real sends. Rendering it in an editable field would invite someone to try.

- [ ] **Step 1: Add the write mutations**

Append to `web/src/api/hooks/content.ts`. The three resources share a shape, so one small factory keeps it honest without becoming an abstraction:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type {
  AssetIn, AssetPatch, CategoryIn, CategoryPatch, QuickReplyIn, QuickReplyPatch,
} from '../types'

function useWrite<TBody, TResult>(path: string, method: 'POST' | 'PATCH' | 'DELETE', invalidate: (propertyId: string) => readonly unknown[]) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TResult, ApiError, TBody & { id?: string }>({
    mutationFn: (body) => {
      const { id, ...rest } = body as { id?: string }
      const url = propertyPath(propertyId, id ? `${path}/${id}` : path)
      return api<TResult>(url, { method, json: method === 'DELETE' ? undefined : rest })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: invalidate(propertyId) })
    },
  })
}

export const useCreateQuickReply = () =>
  useWrite<QuickReplyIn, QuickReplyOut>('quick-replies', 'POST', (p) => qk.quickReplies(p))
export const usePatchQuickReply = () =>
  useWrite<QuickReplyPatch, QuickReplyOut>('quick-replies', 'PATCH', (p) => qk.quickReplies(p))
export const useDeleteQuickReply = () =>
  useWrite<Record<string, never>, void>('quick-replies', 'DELETE', (p) => qk.quickReplies(p))

export const useCreateAsset = () => useWrite<AssetIn, AssetOut>('assets', 'POST', (p) => qk.assets(p))
export const usePatchAsset = () => useWrite<AssetPatch, AssetOut>('assets', 'PATCH', (p) => qk.assets(p))
export const useDeleteAsset = () =>
  useWrite<Record<string, never>, void>('assets', 'DELETE', (p) => qk.assets(p))

export const useCreateCategory = () =>
  useWrite<CategoryIn, CategoryOut>('resolution-categories', 'POST', (p) => qk.categories(p))
export const usePatchCategory = () =>
  useWrite<CategoryPatch, CategoryOut>('resolution-categories', 'PATCH', (p) => qk.categories(p))
export const useDeleteCategory = () =>
  useWrite<Record<string, never>, void>('resolution-categories', 'DELETE', (p) => qk.categories(p))
```

**Note the invalidation key:** `qk.quickReplies(propertyId)` with no `q` produces `['quickReplies', propertyId, '']`, which does **not** match a search-filtered key. Invalidate the prefix instead — use `['quickReplies', propertyId]` so a filtered list refreshes too. Add prefix helpers to `queryKeys.ts`:

```ts
  quickRepliesAll: (propertyId: string) => ['quickReplies', propertyId] as const,
  assetsAll: (propertyId: string) => ['assets', propertyId] as const,
  categoriesAll: (propertyId: string) => ['categories', propertyId] as const,
  staffAll: (propertyId: string) => ['staff', propertyId] as const,
```

and use the `*All` variants in the mutations above. **This is the kind of mismatch that produces a "my edit did not show up" bug with no error anywhere — get it right here.**

Append to `web/src/api/hooks/users.ts`:

```ts
export function useCreateStaff() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffUserOut, ApiError, CreateStaffRequest>({
    mutationFn: (body) => api<StaffUserOut>(propertyPath(propertyId, 'users'), { method: 'POST', json: body }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.staffAll(propertyId) }),
  })
}

export function usePatchStaff() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffUserOut, ApiError, StaffPatch & { id: string }>({
    mutationFn: ({ id, ...patch }) =>
      api<StaffUserOut>(propertyPath(propertyId, `users/${id}`), { method: 'PATCH', json: patch }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.staffAll(propertyId) }),
  })
}

export function useDeleteStaff() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<void, ApiError, { id: string }>({
    mutationFn: ({ id }) => api<void>(propertyPath(propertyId, `users/${id}`), { method: 'DELETE' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.staffAll(propertyId) }),
  })
}
```

- [ ] **Step 2: Write `AdminTable.tsx` and `EditPanel.tsx`**

```tsx
// AdminTable.tsx
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type Column<T> = { key: string; head: string; render: (row: T) => ReactNode; mono?: boolean }

export function AdminTable<T extends { id: string }>({
  columns,
  rows,
  selectedId,
  onSelect,
}: {
  columns: Column<T>[]
  rows: T[]
  selectedId: string | null
  onSelect: (row: T) => void
}) {
  return (
    <table className="w-full">
      <thead>
        <tr>
          {columns.map((column) => (
            <th
              key={column.key}
              className="border-b border-border2 px-3.5 py-2.5 text-left text-[11.5px] font-bold uppercase tracking-wider text-text3"
            >
              {column.head}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.id}
            tabIndex={0}
            aria-selected={row.id === selectedId}
            onClick={() => onSelect(row)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSelect(row)
              }
            }}
            className={cn('cursor-pointer', row.id === selectedId ? 'bg-sel' : 'hover:bg-surface2')}
          >
            {columns.map((column) => (
              <td
                key={column.key}
                className={cn(
                  'border-b border-border px-3.5 py-3 align-top text-[13.5px]',
                  column.mono && 'font-mono',
                )}
              >
                {column.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```

```tsx
// EditPanel.tsx
import { useState, type ReactNode } from 'react'
import { Button } from '../../components/ui'

export function EditPanel({
  title,
  subtitle,
  children,
  onSave,
  onDelete,
  onCancel,
  saving,
  error,
}: {
  title: string
  subtitle?: string
  children: ReactNode
  onSave: () => void
  onDelete?: () => void
  onCancel: () => void
  saving?: boolean
  error?: string | null
}) {
  const [confirming, setConfirming] = useState(false)

  return (
    <aside className="w-[340px] flex-none overflow-y-auto border-l border-border bg-bg2 p-4">
      <header className="mb-3">
        <h2 className="text-sm font-bold">{title}</h2>
        {subtitle ? <p className="text-xs text-text3">{subtitle}</p> : null}
      </header>

      {error ? (
        <p role="alert" className="mb-3 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-3">{children}</div>

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={saving} onClick={onSave}>
          Save
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
        {onDelete ? (
          confirming ? (
            <>
              <span className="w-full text-xs text-dangerText">
                Delete this? This cannot be undone.
              </span>
              <Button variant="danger" onClick={onDelete}>
                Confirm
              </Button>
              <Button onClick={() => setConfirming(false)}>Keep</Button>
            </>
          ) : (
            <Button variant="ghost" className="ml-auto text-dangerText" onClick={() => setConfirming(true)}>
              Delete
            </Button>
          )
        ) : null}
      </footer>
    </aside>
  )
}
```

- [ ] **Step 3: Write the failing quick-replies test**

`web/src/features/admin/QuickRepliesAdmin.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aQuickReply } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { QuickRepliesAdmin } from './QuickRepliesAdmin'

const REPLIES = [
  aQuickReply({ id: 'q1', shortcut: '/wifi', title: 'WiFi details', usageCount: 212 }),
  aQuickReply({ id: 'q2', shortcut: '/shuttle', title: 'Airport shuttle', active: false, usageCount: 0 }),
]

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    if (init && init.method && init.method !== 'GET') {
      return Promise.resolve(
        new Response(JSON.stringify(aQuickReply()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = String(input).includes('/departments') ? [aDepartment()] : REPLIES
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <QuickRepliesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/quick-replies' },
  )
}

describe('QuickRepliesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists replies with shortcut, title and usage', async () => {
    mount()
    expect(await screen.findByText('/wifi')).toBeInTheDocument()
    expect(screen.getByText('WiFi details')).toBeInTheDocument()
    expect(screen.getByText('212')).toBeInTheDocument()
  })

  it('reports the active and inactive counts', async () => {
    mount()
    expect(await screen.findByText(/1 active · 1 inactive/)).toBeInTheDocument()
  })

  it('shows no edit panel until something is selected', async () => {
    mount()
    await screen.findByText('/wifi')
    expect(screen.queryByLabelText('Body')).not.toBeInTheDocument()
  })

  it('opens the edit panel pre-filled when a row is clicked', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await waitFor(() => expect(screen.getByLabelText('Shortcut')).toHaveValue('/wifi'))
    expect(screen.getByLabelText('Title')).toHaveValue('WiFi details')
    expect(screen.getByLabelText('Body')).toHaveValue(REPLIES[0]!.body)
  })

  it('shows usage as read-only text, never as a field', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await waitFor(() => expect(screen.getByText(/212 uses/)).toBeInTheDocument())
    expect(screen.queryByLabelText(/uses/i)).not.toBeInTheDocument()
  })

  it('patches only on save, not on every keystroke', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    const title = await screen.findByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'WiFi info')
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'PATCH')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(String(patch![0])).toContain('/quick-replies/q1')
    expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ title: 'WiFi info' })
  })

  it('creates a new reply through POST', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /new quick reply/i }))
    await userEvent.type(screen.getByLabelText('Shortcut'), '/pool')
    await userEvent.type(screen.getByLabelText('Title'), 'Pool hours')
    await userEvent.type(screen.getByLabelText('Body'), 'The pool is open 7 AM-10 PM.')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({
      shortcut: '/pool',
      title: 'Pool hours',
    })
  })

  it('asks before deleting and only then calls DELETE', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'DELETE')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    const del = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'DELETE')
    expect(String(del![0])).toContain('/quick-replies/q1')
  })

  it('backs out of a delete on Keep', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }))
    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument()
  })

  it('shows the server error in the panel and keeps it open', async () => {
    mount()
    await userEvent.click(await screen.findByText('WiFi details'))
    await screen.findByLabelText('Title')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ error: { code: 'VALIDATION_FAILED', message: 'Shortcut already exists' } }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Shortcut already exists')
    expect(screen.getByLabelText('Title')).toBeInTheDocument()
  })

  it('filters by shortcut or text', async () => {
    mount()
    await screen.findByText('/wifi')
    await userEvent.type(screen.getByPlaceholderText(/search/i), 'shuttle')
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('q=shuttle'))).toBe(true),
    )
  })
})
```

`web/src/features/admin/UsersAdmin.test.tsx` — the role-change path is the one with teeth:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { UsersAdmin } from './UsersAdmin'

const STAFF = [
  aStaffUser({ id: 'u-ava', firstName: 'Ava', lastName: 'Nolan', role: 'agent' }),
  aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer', role: 'dept_staff', departmentId: 'dept-eng' }),
]

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    if (init && init.method && init.method !== 'GET') {
      return Promise.resolve(
        new Response(JSON.stringify(aStaffUser()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = String(input).includes('/departments') ? [aDepartment()] : STAFF
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <UsersAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route: '/app/admin/users' },
  )
}

describe('UsersAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists staff with name, email, role and department', async () => {
    mount()
    expect(await screen.findByText('Ava Nolan')).toBeInTheDocument()
    expect(screen.getByText('ava@hvh.test')).toBeInTheDocument()
    expect(screen.getAllByText(/agent/i).length).toBeGreaterThan(0)
    expect(screen.getByText('Engineering')).toBeInTheDocument()
  })

  it('offers every role in the enum when editing', async () => {
    mount()
    await userEvent.click(await screen.findByText('Ava Nolan'))
    const select = await screen.findByLabelText('Role')
    for (const role of ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']) {
      expect(screen.getByRole('option', { name: role })).toBeInTheDocument()
    }
    expect(select).toHaveValue('agent')
  })

  it('patches the role', async () => {
    mount()
    await userEvent.click(await screen.findByText('Ava Nolan'))
    await userEvent.selectOptions(await screen.findByLabelText('Role'), 'supervisor')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(String(patch![0])).toContain('/users/u-ava')
    expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ role: 'supervisor' })
  })

  it('creates a user with the required identity fields', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /new user/i }))
    await userEvent.type(screen.getByLabelText('First name'), 'Nia')
    await userEvent.type(screen.getByLabelText('Last name'), 'Okafor')
    await userEvent.type(screen.getByLabelText('Email'), 'nia@hvh.test')
    await userEvent.selectOptions(screen.getByLabelText('Role'), 'agent')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({
      firstName: 'Nia',
      lastName: 'Okafor',
      email: 'nia@hvh.test',
      role: 'agent',
    })
  })

  it('will not create a user without an email', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /new user/i }))
    await userEvent.type(screen.getByLabelText('First name'), 'Nia')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })
})
```

`web/src/features/admin/AdminPage.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { AdminPage } from './AdminPage'

function mount(route = '/app/admin/quick-replies') {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/admin/*" element={<AdminPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }), route },
  )
}

describe('AdminPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    ))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists the four live sections as links', async () => {
    mount()
    for (const name of ['Users & roles', 'Quick replies', 'Digital assets', 'Resolution categories']) {
      expect(await screen.findByRole('link', { name })).toBeInTheDocument()
    }
  })

  it('lists the Phase 2 sections as disabled, not as links', async () => {
    mount()
    await screen.findByRole('link', { name: 'Quick replies' })
    for (const name of ['Departments', 'Property settings', 'Automations', 'Blocked numbers', 'Integrations']) {
      expect(screen.getByText(name)).toBeInTheDocument()
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument()
    }
    expect(screen.getByText(/arrive in Phase 2/i)).toBeInTheDocument()
  })

  it('marks the current section', async () => {
    mount('/app/admin/users')
    expect(await screen.findByRole('link', { name: 'Users & roles' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('redirects a bare /app/admin to users', async () => {
    mount('/app/admin')
    expect(await screen.findByRole('link', { name: 'Users & roles' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
```

- [ ] **Step 4: Write the four section screens and `AdminPage.tsx`**

All four follow one shape. `QuickRepliesAdmin.tsx` in full; write the other three the same way, with the columns and fields from the table above.

```tsx
// QuickRepliesAdmin.tsx
import { useState } from 'react'
import {
  useCreateQuickReply, useDeleteQuickReply, usePatchQuickReply, useQuickReplies,
} from '../../api/hooks/content'
import { useDepartments } from '../../api/hooks/users'
import type { QuickReplyOut } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner, Textarea } from '../../components/ui'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'

type Draft = {
  id?: string
  shortcut: string
  title: string
  body: string
  departmentId: string | null
  category: string | null
  locale: string
  active: boolean
}

const EMPTY: Draft = {
  shortcut: '', title: '', body: '', departmentId: null, category: null, locale: 'en', active: true,
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function QuickRepliesAdmin() {
  const [search, setSearch] = useState('')
  const { data, isPending, error } = useQuickReplies(search || undefined)
  const { data: departments } = useDepartments()
  const create = useCreateQuickReply()
  const patch = usePatchQuickReply()
  const remove = useDeleteQuickReply()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<QuickReplyOut | null>(null)

  const rows = data ?? []
  const activeCount = rows.filter((r) => r.active).length
  const pending = create.isPending || patch.isPending || remove.isPending
  const failure = (create.error ?? patch.error ?? remove.error)?.message ?? null

  const columns: Column<QuickReplyOut>[] = [
    { key: 'shortcut', head: 'Shortcut', mono: true, render: (r) => r.shortcut },
    { key: 'title', head: 'Title', render: (r) => r.title },
    {
      key: 'body',
      head: 'Body',
      render: (r) => <span className="text-text3">{r.body.slice(0, 70)}…</span>,
    },
    {
      key: 'dept',
      head: 'Dept',
      render: (r) => departments?.find((d) => d.id === r.departmentId)?.name ?? 'All',
    },
    { key: 'uses', head: 'Uses', mono: true, render: (r) => r.usageCount },
    {
      key: 'active',
      head: 'Active',
      render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>),
    },
  ]

  function open(reply: QuickReplyOut) {
    setSelected(reply)
    setDraft({
      id: reply.id,
      shortcut: reply.shortcut,
      title: reply.title,
      body: reply.body,
      departmentId: reply.departmentId,
      category: reply.category,
      locale: reply.locale,
      active: reply.active,
    })
  }

  function save() {
    if (!draft || !draft.shortcut.trim() || !draft.title.trim() || !draft.body.trim()) return
    const done = () => {
      setDraft(null)
      setSelected(null)
    }
    if (draft.id) patch.mutate(draft, { onSuccess: done })
    else create.mutate(draft, { onSuccess: done })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <div>
            <h1 className="text-base font-bold">Quick replies</h1>
            <p className="text-xs text-text3">
              {activeCount} active · {rows.length - activeCount} inactive
            </p>
          </div>
          <Input
            className="ml-4 max-w-xs"
            placeholder="Search shortcut or text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              setSelected(null)
              setDraft({ ...EMPTY })
            }}
          >
            New quick reply
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load quick replies" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No quick replies" hint="Create one to get started." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          title={draft.id ? 'Edit quick reply' : 'New quick reply'}
          subtitle={selected ? `${selected.usageCount} uses` : undefined}
          saving={pending}
          error={failure}
          onSave={save}
          onCancel={() => {
            setDraft(null)
            setSelected(null)
          }}
          onDelete={
            draft.id
              ? () =>
                  remove.mutate({ id: draft.id } as never, {
                    onSuccess: () => {
                      setDraft(null)
                      setSelected(null)
                    },
                  })
              : undefined
          }
        >
          <div>
            <label className={LABEL} htmlFor="qr-shortcut">Shortcut</label>
            <Input id="qr-shortcut" value={draft.shortcut}
                   onChange={(e) => setDraft({ ...draft, shortcut: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-title">Title</label>
            <Input id="qr-title" value={draft.title}
                   onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-body">Body</label>
            <Textarea id="qr-body" rows={6} value={draft.body}
                      onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
            <p className="mt-1 text-xs text-text3">
              {'{{guest_first_name}}'} and {'{{room_number}}'} are filled in when sent.
            </p>
          </div>
          <div>
            <label className={LABEL} htmlFor="qr-dept">Department</label>
            <select id="qr-dept" className={SELECT} value={draft.departmentId ?? ''}
                    onChange={(e) => setDraft({ ...draft, departmentId: e.target.value || null })}>
              <option value="">All</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active}
                   onChange={(e) => setDraft({ ...draft, active: e.target.checked })} />
            Active
          </label>
        </EditPanel>
      ) : null}
    </div>
  )
}
```

`AdminPage.tsx` — the sub-nav plus the nested routes:

```tsx
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { cn } from '../../lib/cn'
import { AssetsAdmin } from './AssetsAdmin'
import { CategoriesAdmin } from './CategoriesAdmin'
import { QuickRepliesAdmin } from './QuickRepliesAdmin'
import { UsersAdmin } from './UsersAdmin'

const LIVE = [
  { to: 'users', label: 'Users & roles' },
  { to: 'quick-replies', label: 'Quick replies' },
  { to: 'assets', label: 'Digital assets' },
  { to: 'categories', label: 'Resolution categories' },
]

// Shown deliberately (mockup Admin.dc.html): an admin should see the product's shape.
const PHASE_2 = ['Departments', 'Property settings', 'Automations', 'Blocked numbers', 'Integrations']

export function AdminPage() {
  return (
    <div className="flex h-full">
      <nav className="w-[220px] flex-none border-r border-border p-3">
        <h1 className="mb-3 px-2 text-base font-bold">Admin</h1>
        <ul className="flex flex-col gap-0.5">
          {LIVE.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex h-10 items-center rounded px-3 text-sm font-semibold',
                    isActive
                      ? 'bg-surface2 text-text shadow-[inset_3px_0_0_var(--accent)]'
                      : 'text-text3 hover:text-text',
                  )
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
          {PHASE_2.map((label) => (
            <li
              key={label}
              aria-disabled="true"
              className="flex h-10 cursor-not-allowed items-center rounded px-3 text-sm font-semibold text-text4"
            >
              {label}
            </li>
          ))}
        </ul>
        <p className="mt-3 px-3 text-xs text-text4">Greyed items arrive in Phase 2</p>
      </nav>

      <Routes>
        <Route index element={<Navigate to="users" replace />} />
        <Route path="users" element={<UsersAdmin />} />
        <Route path="quick-replies" element={<QuickRepliesAdmin />} />
        <Route path="assets" element={<AssetsAdmin />} />
        <Route path="categories" element={<CategoriesAdmin />} />
      </Routes>
    </div>
  )
}
```

In `routes.tsx`, replace the `admin/*` placeholder with `<AdminPage />` (keeping `RequireCapability`).

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 11 quick-reply tests, 5 user tests, 4 admin-page tests.

- [ ] **Step 6: Verify against the real server**

As `alex@hvh.test`, visit each of the four sections. Edit a quick reply's body and confirm the change shows in the inbox palette immediately (this is the `*All` invalidation key from Step 1 working — if the table updates but the palette does not, the key is wrong). Create a quick reply, use it in a conversation, delete it. Change a user's role and confirm that user's nav changes on their next load. Add a category and use it when archiving. Confirm the Phase 2 rows are visibly disabled and do nothing.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/admin web/src/api/hooks/content.ts web/src/api/hooks/users.ts \
        web/src/api/queryKeys.ts web/src/routes.tsx
git commit -m "feat(web): admin CRUD for users, quick replies, assets and categories"
```

---

