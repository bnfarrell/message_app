### Task 15: Draft prompts, work-order creation, assignment, snooze, archive

**Files:**
- Create: `web/src/features/inbox/DraftPromptBanner.tsx`, `CreateWorkOrderModal.tsx`, `ArchiveDialog.tsx`, `ConversationActions.tsx`
- Create: `web/src/api/hooks/workOrders.ts`
- Modify: `web/src/features/inbox/ConversationView.tsx` (mount banner + actions), `ConversationHeader.tsx` (host the actions)
- Test: `web/src/features/inbox/DraftPromptBanner.test.tsx`, `CreateWorkOrderModal.test.tsx`, `ArchiveDialog.test.tsx`, `ConversationActions.test.tsx`

**Interfaces:**
- Consumes: `usePatchConversation` / `useConversation` (Tasks 12-13), `useDepartments` / `useStaff` (Task 12), `useCategories` (Task 14), `Dialog` / `Dropdown` / `Button` / `Input` / `Textarea` / `useToast` (Task 4), factories (Task 12).
- Produces:
  - `workOrders.ts`: `useWorkOrders(params)`, `useWorkOrder(id)`, `useWorkOrderPrefill(conversationId | undefined)`, `useCreateWorkOrder()`, `usePatchWorkOrder(id)`
  - `DraftPromptBanner({ conversation, onUseDraft })`, `CreateWorkOrderModal({ conversationId, open, onClose })`, `ArchiveDialog({ conversationId, open, onClose })`, `ConversationActions({ conversation })`

**Draft prompt banner (§5.3), above the composer.** Shown only when `can('reply')` — the dismiss route is `@require_capability("reply")` too (`server/app/api/conversations.py:110`), so corporate must not see either button.
 For each `draftPrompts` entry with `status: 'pending'`, render `bg-okBanner`-adjacent treatment — use `border-okBorder bg-okBg text-okText` so it reads as good news in both palettes — with the copy pattern from §5.3:

> Work order #204 (AC not cooling, 412) is complete. Let Sarah know?

built from `workOrderId`, `workOrderTitle`, the conversation's room number and the guest's first name, plus two buttons: **Use draft** (loads `prompt.body` into the composer and carries `draftPromptId` through on send, so the server marks the prompt sent and stamps `guest_notified_at`) and **Dismiss** (`POST conversations/<id>/draft-prompts/<pid>/dismiss`). The work-order id renders in mono. A guest with no first name falls back to "the guest".

**Create work order modal (§5.3).** Opens pre-filled from `GET work-orders/prefill?conversationId=`, which returns `title`, `description`, `locationType`, `locationRef`, `type`, `priority`, `departmentId`, `guestName`, `sourceConversationId`, `sourceMessageId`. Editable fields: title, description, type, priority, department, assignee (optional), location ref. On save, `POST work-orders` carrying `sourceConversationId` and `sourceMessageId` from the prefill unchanged — that link is what §11.1 #6 asserts and what makes the closed loop possible. On success, invalidate the conversation (the panel gains the WO) and the board lists, toast the new id, and close. The **Create work order** button is shown only when `can('create_work_order')`.

**Assignment and snooze** sit in `ConversationActions`, in the header, matching the mockup's `Assign` / `Snooze` buttons:
- **Assign** — a `Dropdown` listing staff (`useStaff`) then departments (`useDepartments`), plus **Unassign** which sends `{ clearAssignment: true }`. Shown when `can('assign')`.
- **Snooze** — presets of 1 hour, 4 hours and tomorrow 9 am local, sending `{ snoozedUntil: <ISO> }`. Tomorrow-9 am is computed in the browser's zone, which is the property's zone in practice; the server stores the instant.
- **Archive** — opens `ArchiveDialog`. Shown when `can('archive')`.

**Archive dialog (§5.3).** Asks for an *optional* resolution category, from `useCategories()` (a tree: parents with `children`). Renders as a flat `<select>` with `—` for "no category" and indented child names, because the seeded tree is two levels and a real tree widget is unearned here. On confirm, `PATCH { status: 'archived', resolutionCategoryId }`. The category is optional — forcing one would make agents pick a wrong value to clear their queue.

- [ ] **Step 1: Write `web/src/api/hooks/workOrders.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  CreateWorkOrder,
  WorkOrderDetail,
  WorkOrderOut,
  WorkOrderPatch,
  WorkOrderPrefill,
} from '../types'

export type WorkOrderParams = {
  status?: string | null
  type?: string | null
  dept?: string | null
  assignee?: string | null
  mine?: boolean
  includeClosed?: boolean
}

export function useWorkOrders(params: WorkOrderParams = {}) {
  const { propertyId } = useSession()
  const search = new URLSearchParams()
  if (params.status) search.set('status', params.status)
  if (params.type) search.set('type', params.type)
  if (params.dept) search.set('dept', params.dept)
  if (params.assignee) search.set('assignee', params.assignee)
  if (params.mine) search.set('mine', 'true')
  if (params.includeClosed) search.set('includeClosed', 'true')

  return useQuery<WorkOrderOut[], ApiError>({
    queryKey: qk.workOrders(propertyId, { ...params } as Record<string, string | boolean | null>),
    queryFn: () =>
      api<WorkOrderOut[]>(propertyPath(propertyId, `work-orders${search.size ? `?${search}` : ''}`)),
  })
}

export function useWorkOrder(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<WorkOrderDetail, ApiError>({
    queryKey: qk.workOrder(propertyId, id ?? ''),
    queryFn: () => api<WorkOrderDetail>(propertyPath(propertyId, `work-orders/${id}`)),
    enabled: Boolean(id),
  })
}

export function useWorkOrderPrefill(conversationId: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<WorkOrderPrefill, ApiError>({
    queryKey: qk.workOrderPrefill(propertyId, conversationId ?? ''),
    queryFn: () =>
      api<WorkOrderPrefill>(
        propertyPath(propertyId, `work-orders/prefill?conversationId=${conversationId}`),
      ),
    enabled: Boolean(conversationId),
    staleTime: 0, // the suggestion depends on the last inbound message
  })
}

export function useCreateWorkOrder() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<WorkOrderOut, ApiError, CreateWorkOrder>({
    mutationFn: (body) =>
      api<WorkOrderOut>(propertyPath(propertyId, 'work-orders'), { method: 'POST', json: body }),
    onSuccess: (created) => {
      void client.invalidateQueries({ queryKey: qk.workOrdersAll(propertyId) })
      if (created.sourceConversationId) {
        void client.invalidateQueries({
          queryKey: qk.conversation(propertyId, created.sourceConversationId),
        })
      }
    },
  })
}

export function usePatchWorkOrder(id: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<WorkOrderDetail, ApiError, WorkOrderPatch>({
    mutationFn: (patch) =>
      api<WorkOrderDetail>(propertyPath(propertyId, `work-orders/${id}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: (updated) => {
      void client.invalidateQueries({ queryKey: qk.workOrder(propertyId, id) })
      void client.invalidateQueries({ queryKey: qk.workOrdersAll(propertyId) })
      // Completing a WO raised from a conversation creates a draft prompt there.
      if (updated.sourceConversationId) {
        void client.invalidateQueries({
          queryKey: qk.conversation(propertyId, updated.sourceConversationId),
        })
      }
    },
  })
}
```

- [ ] **Step 2: Write the failing tests**

`web/src/features/inbox/DraftPromptBanner.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversationDetail, aDraftPrompt, aGuest } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { DraftPromptBanner } from './DraftPromptBanner'

function mount(detail = aConversationDetail({ draftPrompts: [aDraftPrompt()] }), onUse = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <DraftPromptBanner conversation={detail} onUseDraft={onUse} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
  return onUse
}

describe('DraftPromptBanner', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders nothing when there is no pending prompt', () => {
    const { container } = renderWithProviders(
      <SessionProvider>
        <DraftPromptBanner conversation={aConversationDetail()} onUseDraft={vi.fn()} />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    expect(container.querySelector('[data-testid="draft-prompt"]')).toBeNull()
  })

  it('renders nothing for a prompt that is already sent or dismissed', () => {
    const { container } = renderWithProviders(
      <SessionProvider>
        <DraftPromptBanner
          conversation={aConversationDetail({ draftPrompts: [aDraftPrompt({ status: 'sent' })] })}
          onUseDraft={vi.fn()}
        />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    expect(container.querySelector('[data-testid="draft-prompt"]')).toBeNull()
  })

  it('states the work order, its title, the room and the guest (§5.3 copy)', async () => {
    mount()
    const banner = await screen.findByTestId('draft-prompt')
    expect(banner).toHaveTextContent('AC not cooling')
    expect(banner).toHaveTextContent('412')
    expect(banner).toHaveTextContent('Sarah')
    expect(banner).toHaveTextContent(/is complete/i)
  })

  it('falls back to "the guest" when the guest has no first name', async () => {
    mount(
      aConversationDetail({
        guest: aGuest({ firstName: null, lastName: null }),
        draftPrompts: [aDraftPrompt()],
      }),
    )
    expect(await screen.findByTestId('draft-prompt')).toHaveTextContent('the guest')
  })

  it('hands the draft body up on Use draft', async () => {
    const onUse = mount()
    await userEvent.click(await screen.findByRole('button', { name: /use draft/i }))
    expect(onUse).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'd-1', body: expect.stringContaining('engineering') }),
    )
  })

  it('dismisses through the API', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /dismiss/i }))
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([u]) => String(u).includes('/draft-prompts/d-1/dismiss'))
    expect(call).toBeDefined()
    expect(call![1]).toMatchObject({ method: 'POST' })
  })

  it('shows every pending prompt, not just the first', async () => {
    mount(
      aConversationDetail({
        draftPrompts: [aDraftPrompt({ id: 'd-1' }), aDraftPrompt({ id: 'd-2', workOrderId: 'w-9' })],
      }),
    )
    expect(await screen.findAllByTestId('draft-prompt')).toHaveLength(2)
  })
})
```

`web/src/features/inbox/CreateWorkOrderModal.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { aDepartment, aStaffUser, aWorkOrder } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { CreateWorkOrderModal } from './CreateWorkOrderModal'

const PREFILL = {
  title: 'AC not cooling',
  description: "Guest reports the AC in 412 isn't working at all and the room is warm.",
  type: 'maintenance',
  priority: 'urgent',
  locationType: 'room',
  locationRef: '412',
  departmentId: 'dept-eng',
  guestName: 'Sarah Chen',
  sourceConversationId: 'c-1',
  sourceMessageId: 'm-1',
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/work-orders') && init?.method === 'POST') {
      return Promise.resolve(
        new Response(JSON.stringify(aWorkOrder({ id: 'w-500' })), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = url.includes('prefill')
      ? PREFILL
      : url.includes('/departments')
        ? [aDepartment(), aDepartment({ id: 'dept-hk', name: 'Housekeeping', type: 'housekeeping' })]
        : url.includes('/users')
          ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer', role: 'dept_staff' })]
          : []
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(onClose = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <CreateWorkOrderModal conversationId="c-1" open onClose={onClose} />
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
  return onClose
}

describe('CreateWorkOrderModal', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('pre-fills from the server suggestion (§5.3)', async () => {
    mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    expect(screen.getByLabelText('Description')).toHaveValue(PREFILL.description)
    expect(screen.getByLabelText('Location')).toHaveValue('412')
    expect(screen.getByLabelText('Priority')).toHaveValue('urgent')
    expect(screen.getByLabelText('Department')).toHaveValue('dept-eng')
  })

  it('lets the agent edit before saving', async () => {
    mount()
    const title = await screen.findByLabelText('Title')
    await waitFor(() => expect(title).toHaveValue('AC not cooling'))
    await userEvent.clear(title)
    await userEvent.type(title, 'AC dead in 412')
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({ title: 'AC dead in 412' })
  })

  it('carries the conversation and message link through unchanged (§11.1 #6)', async () => {
    mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({
      sourceConversationId: 'c-1',
      sourceMessageId: 'm-1',
    })
  })

  it('will not save an empty title', async () => {
    mount()
    const title = await screen.findByLabelText('Title')
    await waitFor(() => expect(title).toHaveValue('AC not cooling'))
    await userEvent.clear(title)
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })

  it('closes on success', async () => {
    const onClose = mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('shows the server error and stays open on failure', async () => {
    const onClose = mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'FORBIDDEN', message: 'Not allowed' } }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Not allowed')
    expect(onClose).not.toHaveBeenCalled()
  })
})
```

`web/src/features/inbox/ArchiveDialog.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversationDetail } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ArchiveDialog } from './ArchiveDialog'

const CATEGORIES = [
  {
    id: 'cat-maint',
    name: 'Maintenance',
    parentId: null,
    active: true,
    children: [
      { id: 'cat-hvac', name: 'HVAC', parentId: 'cat-maint', active: true, children: [] },
      { id: 'cat-plumb', name: 'Plumbing', parentId: 'cat-maint', active: true, children: [] },
    ],
  },
  { id: 'cat-praise', name: 'Praise', parentId: null, active: true, children: [] },
]

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PATCH') {
      return Promise.resolve(
        new Response(JSON.stringify(aConversationDetail({ status: 'archived' })), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    return Promise.resolve(
      new Response(JSON.stringify(url.includes('resolution-categories') ? CATEGORIES : []), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(onClose = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <ArchiveDialog conversationId="c-1" open onClose={onClose} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
  return onClose
}

describe('ArchiveDialog', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('offers the category tree flattened, parents and children', async () => {
    mount()
    const select = await screen.findByLabelText(/resolution category/i)
    await waitFor(() => expect(select).toHaveDisplayValue('—'))
    expect(screen.getByRole('option', { name: 'Maintenance' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /HVAC/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Praise' })).toBeInTheDocument()
  })

  it('archives with no category, because the category is optional (§5.3)', async () => {
    mount()
    await screen.findByLabelText(/resolution category/i)
    await userEvent.click(screen.getByRole('button', { name: /archive/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({
      status: 'archived',
      resolutionCategoryId: null,
    })
  })

  it('archives with the chosen category', async () => {
    mount()
    const select = await screen.findByLabelText(/resolution category/i)
    await waitFor(() => expect(screen.getByRole('option', { name: /HVAC/ })).toBeInTheDocument())
    await userEvent.selectOptions(select, 'cat-hvac')
    await userEvent.click(screen.getByRole('button', { name: /archive/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toMatchObject({ resolutionCategoryId: 'cat-hvac' })
  })

  it('closes on success', async () => {
    const onClose = mount()
    await screen.findByLabelText(/resolution category/i)
    await userEvent.click(screen.getByRole('button', { name: /archive/i }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})
```

`web/src/features/inbox/ConversationActions.test.tsx` — the role gating and the snooze payload:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { aConversationDetail, aDepartment, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ConversationActions } from './ConversationActions'

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PATCH') {
      return Promise.resolve(
        new Response(JSON.stringify(aConversationDetail()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-marcus', firstName: 'Marcus', lastName: 'Reyes' })]
        : []
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(role: Role = 'agent') {
  renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <ConversationActions conversation={aConversationDetail()} />
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role }), route: '/app/inbox/c-1' },
  )
}

describe('ConversationActions', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-09-10T19:00:00Z'))
    serve()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('offers Assign, Snooze, Archive and Create work order to an agent', async () => {
    mount('agent')
    expect(await screen.findByRole('button', { name: /assign/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /snooze/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /archive/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /work order/i })).toBeInTheDocument()
  })

  it('hides Archive from dept_staff, who lack the capability', async () => {
    mount('dept_staff')
    expect(await screen.findByRole('button', { name: /assign/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /archive/i })).not.toBeInTheDocument()
  })

  it('hides every write action from corporate', async () => {
    mount('corporate')
    await waitFor(() => expect(screen.queryByRole('button', { name: /assign/i })).not.toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /work order/i })).not.toBeInTheDocument()
  })

  it('assigns to a person', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /assign/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Marcus Reyes/ }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ assignedUserId: 'u-marcus' })
  })

  it('assigns to a department', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /assign/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Engineering/ }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ assignedDepartmentId: 'dept-eng' })
  })

  it('unassigns with the explicit clear flag', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /assign/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /unassign/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ clearAssignment: true })
  })

  it('snoozes an hour out', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /snooze/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /1 hour/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    const body = JSON.parse(String(patch![1]!.body)) as { snoozedUntil: string }
    expect(new Date(body.snoozedUntil).getTime()).toBe(
      new Date('2026-09-10T20:00:00Z').getTime(),
    )
  })
})
```

- [ ] **Step 3: Run them to verify they fail**

```bash
cd web && npx vitest run src/features/inbox
```

Expected: FAIL — the four new modules do not resolve.

- [ ] **Step 4: Write `DraftPromptBanner.tsx`**

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, propertyPath, type ApiError } from '../../api/client'
import { qk } from '../../api/queryKeys'
import type { ConversationDetail, DraftPromptOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button } from '../../components/ui'

function useDismissPrompt(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<void, ApiError, { promptId: string }>({
    mutationFn: ({ promptId }) =>
      api<void>(
        propertyPath(propertyId, `conversations/${conversationId}/draft-prompts/${promptId}/dismiss`),
        { method: 'POST' },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.conversation(propertyId, conversationId) })
    },
  })
}

export function DraftPromptBanner({
  conversation,
  onUseDraft,
}: {
  conversation: ConversationDetail
  onUseDraft: (prompt: DraftPromptOut) => void
}) {
  const dismiss = useDismissPrompt(conversation.id)
  const { can } = useSession()
  const pending = conversation.draftPrompts.filter((p) => p.status === 'pending')
  // Both buttons hit routes gated on `reply` (the dismiss route included), so a role
  // that cannot reply must not be offered them — the click would 403.
  if (pending.length === 0 || !can('reply')) return null

  const guestName = conversation.guest.firstName ?? 'the guest'
  const room = conversation.stay?.roomNumber

  return (
    <div className="flex flex-col gap-2 px-3 pt-3">
      {pending.map((prompt) => (
        <div
          key={prompt.id}
          data-testid="draft-prompt"
          className="flex flex-wrap items-center gap-3 rounded-card border border-okBorder bg-okBg px-3.5 py-3 text-sm text-okText"
        >
          <p className="min-w-0 flex-1">
            Work order <span className="font-mono font-bold">#{prompt.workOrderId}</span> (
            {prompt.workOrderTitle}
            {room ? `, ${room}` : ''}) is complete. Let {guestName} know?
          </p>
          <Button variant="primary" onClick={() => onUseDraft(prompt)}>
            Use draft
          </Button>
          <Button onClick={() => dismiss.mutate({ promptId: prompt.id })}>Dismiss</Button>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Write `CreateWorkOrderModal.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { useCreateWorkOrder, useWorkOrderPrefill } from '../../api/hooks/workOrders'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { CreateWorkOrder, Priority, WorkOrderType } from '../../api/types'
import { Button, Dialog, Input, Spinner, Textarea, useToast } from '../../components/ui'

const TYPES: WorkOrderType[] = ['maintenance', 'housekeeping', 'guest_request', 'pm', 'other']
const PRIORITIES: Priority[] = ['low', 'normal', 'high', 'urgent']

const FIELD = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT =
  'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function CreateWorkOrderModal({
  conversationId,
  open,
  onClose,
}: {
  conversationId: string
  open: boolean
  onClose: () => void
}) {
  const prefill = useWorkOrderPrefill(open ? conversationId : undefined)
  const create = useCreateWorkOrder()
  const { data: departments } = useDepartments()
  const { data: staff } = useStaff()
  const toast = useToast()
  const [form, setForm] = useState<CreateWorkOrder | null>(null)

  // Seed the form once the suggestion lands; the agent owns it from then on.
  useEffect(() => {
    if (prefill.data && !form) {
      setForm({
        title: prefill.data.title,
        description: prefill.data.description,
        type: prefill.data.type,
        priority: prefill.data.priority,
        locationType: prefill.data.locationType,
        locationRef: prefill.data.locationRef,
        departmentId: prefill.data.departmentId,
        assignedUserId: null,
        dueAt: null,
        sourceConversationId: prefill.data.sourceConversationId,
        sourceMessageId: prefill.data.sourceMessageId,
      })
    }
  }, [prefill.data, form])

  function set<K extends keyof CreateWorkOrder>(key: K, value: CreateWorkOrder[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current))
  }

  function submit() {
    if (!form || !form.title.trim()) return
    create.mutate(form, {
      onSuccess: (created) => {
        toast(`Work order #${created.id} created`)
        setForm(null)
        onClose()
      },
    })
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Create work order"
      wide
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={create.isPending} onClick={submit}>
            Create
          </Button>
        </>
      }
    >
      {!form ? (
        <div className="grid place-items-center py-8">
          <Spinner />
        </div>
      ) : (
        <>
          {create.error ? (
            <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
              {create.error.message}
            </p>
          ) : null}

          {prefill.data?.guestName ? (
            <p className="text-xs text-text3">
              Pre-filled from {prefill.data.guestName}&rsquo;s message.
            </p>
          ) : null}

          <div>
            <label className={FIELD} htmlFor="wo-title">Title</label>
            <Input id="wo-title" value={form.title} onChange={(e) => set('title', e.target.value)} />
          </div>

          <div>
            <label className={FIELD} htmlFor="wo-desc">Description</label>
            <Textarea
              id="wo-desc"
              rows={4}
              value={form.description ?? ''}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={FIELD} htmlFor="wo-type">Type</label>
              <select id="wo-type" className={SELECT} value={form.type}
                      onChange={(e) => set('type', e.target.value as WorkOrderType)}>
                {TYPES.map((t) => (
                  <option key={t} value={t}>{t.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={FIELD} htmlFor="wo-priority">Priority</label>
              <select id="wo-priority" className={SELECT} value={form.priority}
                      onChange={(e) => set('priority', e.target.value as Priority)}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={FIELD} htmlFor="wo-dept">Department</label>
              <select id="wo-dept" className={SELECT} value={form.departmentId ?? ''}
                      onChange={(e) => set('departmentId', e.target.value || null)}>
                <option value="">—</option>
                {(departments ?? []).map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={FIELD} htmlFor="wo-assignee">Assignee</label>
              <select id="wo-assignee" className={SELECT} value={form.assignedUserId ?? ''}
                      onChange={(e) => set('assignedUserId', e.target.value || null)}>
                <option value="">Unassigned</option>
                {(staff ?? []).map((s) => (
                  <option key={s.id} value={s.id}>{s.firstName} {s.lastName}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className={FIELD} htmlFor="wo-location">Location</label>
            <Input
              id="wo-location"
              value={form.locationRef ?? ''}
              onChange={(e) => set('locationRef', e.target.value)}
            />
          </div>
        </>
      )}
    </Dialog>
  )
}
```

- [ ] **Step 6: Write `ArchiveDialog.tsx`**

```tsx
import { useState } from 'react'
import { useCategories } from '../../api/hooks/content'
import { usePatchConversation } from '../../api/hooks/conversations'
import type { CategoryOut } from '../../api/types'
import { Button, Dialog } from '../../components/ui'

/** Two levels is all the seed has; a tree widget here would be unearned. */
function flatten(categories: CategoryOut[], depth = 0): { id: string; label: string }[] {
  return categories.flatMap((category) => [
    { id: category.id, label: `${'  '.repeat(depth)}${category.name}` },
    ...flatten(category.children ?? [], depth + 1),
  ])
}

export function ArchiveDialog({
  conversationId,
  open,
  onClose,
}: {
  conversationId: string
  open: boolean
  onClose: () => void
}) {
  const { data: categories } = useCategories()
  const patch = usePatchConversation(conversationId)
  const [categoryId, setCategoryId] = useState('')
  const options = flatten((categories ?? []).filter((c) => c.active))

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Archive conversation"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={patch.isPending}
            onClick={() =>
              patch.mutate(
                { status: 'archived', resolutionCategoryId: categoryId || null },
                { onSuccess: onClose },
              )
            }
          >
            Archive
          </Button>
        </>
      }
    >
      {patch.error ? (
        <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {patch.error.message}
        </p>
      ) : null}
      <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-text3" htmlFor="archive-cat">
        Resolution category
      </label>
      <select
        id="archive-cat"
        className="h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none"
        value={categoryId}
        onChange={(event) => setCategoryId(event.target.value)}
      >
        <option value="">—</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>{option.label}</option>
        ))}
      </select>
      <p className="text-xs text-text3">Optional. Leave blank if none fits.</p>
    </Dialog>
  )
}
```

- [ ] **Step 7: Write `ConversationActions.tsx`**

```tsx
import { useState } from 'react'
import { usePatchConversation } from '../../api/hooks/conversations'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { ConversationDetail } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, Dropdown } from '../../components/ui'
import { ArchiveDialog } from './ArchiveDialog'
import { CreateWorkOrderModal } from './CreateWorkOrderModal'

function snoozePresets(now: Date): { label: string; at: Date }[] {
  const hour = (n: number) => new Date(now.getTime() + n * 3600_000)
  const tomorrow9 = new Date(now)
  tomorrow9.setDate(tomorrow9.getDate() + 1)
  tomorrow9.setHours(9, 0, 0, 0)
  return [
    { label: '1 hour', at: hour(1) },
    { label: '4 hours', at: hour(4) },
    { label: 'Tomorrow 9 am', at: tomorrow9 },
  ]
}

const ITEM = 'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface2'

export function ConversationActions({ conversation }: { conversation: ConversationDetail }) {
  const { can } = useSession()
  const patch = usePatchConversation(conversation.id)
  const { data: staff } = useStaff()
  const { data: departments } = useDepartments()
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [woOpen, setWoOpen] = useState(false)

  return (
    <div className="flex items-center gap-2">
      {can('assign') ? (
        <Dropdown label="Assign" align="right">
          {(close) => (
            <>
              {(staff ?? []).map((person) => (
                <button
                  key={person.id}
                  role="menuitem"
                  className={ITEM}
                  onClick={() => {
                    close()
                    patch.mutate({ assignedUserId: person.id })
                  }}
                >
                  {person.firstName} {person.lastName}
                </button>
              ))}
              <hr className="my-1 border-border" />
              {(departments ?? []).map((department) => (
                <button
                  key={department.id}
                  role="menuitem"
                  className={ITEM}
                  onClick={() => {
                    close()
                    patch.mutate({ assignedDepartmentId: department.id })
                  }}
                >
                  {department.name}
                </button>
              ))}
              <hr className="my-1 border-border" />
              <button
                role="menuitem"
                className={ITEM}
                onClick={() => {
                  close()
                  // The server needs the explicit flag; a null would read as "no change".
                  patch.mutate({ clearAssignment: true })
                }}
              >
                Unassign
              </button>
            </>
          )}
        </Dropdown>
      ) : null}

      {can('assign') ? (
        <Dropdown label="Snooze" align="right">
          {(close) => (
            <>
              {snoozePresets(new Date()).map((preset) => (
                <button
                  key={preset.label}
                  role="menuitem"
                  className={ITEM}
                  onClick={() => {
                    close()
                    patch.mutate({ snoozedUntil: preset.at.toISOString() })
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </>
          )}
        </Dropdown>
      ) : null}

      {can('create_work_order') ? (
        <Button onClick={() => setWoOpen(true)}>Create work order</Button>
      ) : null}

      {can('archive') ? <Button onClick={() => setArchiveOpen(true)}>Archive</Button> : null}

      <ArchiveDialog
        conversationId={conversation.id}
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
      />
      <CreateWorkOrderModal
        conversationId={conversation.id}
        open={woOpen}
        onClose={() => setWoOpen(false)}
      />
    </div>
  )
}
```

- [ ] **Step 8: Wire the banner and actions into the conversation**

In `ConversationHeader.tsx`, render `<ConversationActions conversation={conversation} />` in the right-hand group, after the SLA chip.

In `ConversationView.tsx`, hold the handed-down draft and pass it to the composer:

```tsx
const [draft, setDraft] = useState<{ body: string; promptId: string } | null>(null)
// …between the timeline and the composer:
<DraftPromptBanner
  conversation={data}
  onUseDraft={(prompt) => setDraft({ body: prompt.body, promptId: prompt.id })}
/>
<Composer
  conversationId={conversationId}
  conversation={data}
  draftBody={draft?.body}
  draftPromptId={draft?.promptId}
  onDraftConsumed={() => setDraft(null)}
/>
```

- [ ] **Step 9: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 7 banner tests, 6 modal tests, 5 archive tests, 8 action tests.

- [ ] **Step 10: Verify the closed loop against the real server**

This is §11.1's loop, by hand, and the single most valuable check in the plan:
1. As Ava on the 412 conversation, click **Create work order**. The modal pre-fills with the AC text, room 412 and Engineering. Save; the panel gains the work order.
2. In a second browser profile as `eli@hvh.test`, open `/app/board`, find that work order, and move it to **In progress** then **Complete**.
3. Back as Ava — **without reloading** — the green draft-prompt banner appears above the composer naming the work order and Sarah.
4. Click **Use draft**: the composer fills with the draft. Send. The prompt disappears and the work order's `guestNotifiedAt` is set (visible on its detail in Task 16).
5. Also confirm **Dismiss** removes a prompt without sending, and that the two seeded conversations with pending prompts show banners on first load.

- [ ] **Step 11: Commit**

```bash
git add web/src/features/inbox web/src/api/hooks/workOrders.ts
git commit -m "feat(web): draft prompts, work-order creation from a conversation, assign, snooze, archive"
```

---

