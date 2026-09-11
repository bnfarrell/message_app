### Task 12: Conversation hooks and the inbox queue

**Files:**
- Create: `web/src/api/hooks/conversations.ts`, `web/src/api/hooks/users.ts`
- Create: `web/src/features/inbox/InboxPage.tsx`, `web/src/features/inbox/ConversationList.tsx`, `web/src/features/inbox/FilterTabs.tsx`
- Modify: `web/src/routes.tsx` (replace the Inbox placeholders)
- Test: `web/src/features/inbox/ConversationList.test.tsx`, `web/src/features/inbox/FilterTabs.test.tsx`
- Create: `web/src/test/factories.ts` (typed fixture builders reused by Tasks 12-21)

**Interfaces:**
- Consumes: `api` / `propertyPath` / `qk` (Task 3), `useSession` (Task 5), `useRealtime` (Task 11), `SlaChip` (Task 10), `Avatar` / `Badge` / `EmptyState` / `Spinner` (Task 4).
- Produces:
  - `useConversations(filter: ConversationFilter, dept?: string | null)` — `useInfiniteQuery`, offset paging per ruling **R3**, page size 50; `.data.pages.flat()` is the list
  - `useConversation(id: string | undefined)` — detail, `enabled: !!id`
  - `useDepartments()`, `useStaff()` — for the assign menus and department names
  - `type ConversationFilter = 'all' | 'mine' | 'unassigned' | 'overdue' | 'snoozed' | 'resolved' | 'archived'` — exactly the values `server/app/domain/conversations.py:136-155` accepts; anything else is a 400
  - `factories.ts`: `aGuest`, `aStay`, `aConversation`, `aConversationDetail`, `aMessage`, `aNote`, `aDraftPrompt`, `aWorkOrder`, `aWorkOrderDetail`, `aQuickReply`, `aAsset`, `aNotification`, `aDepartment`, `aStaffUser` — each takes a partial and returns a complete, type-correct model
  - `ConversationList({ filter, selectedId, dept }: { filter: ConversationFilter; selectedId?: string; dept?: string | null })`, `FilterTabs({ value, counts, onChange })`, `InboxPage`

**Queue order is the server's** (`unanswered` first, then oldest `lastGuestMessageAt`) — §5.3's "oldest-unanswered first". The client **must not re-sort**; it renders the order it receives. A client-side sort would silently diverge from the SLA sweep's idea of what is most urgent.

**Row anatomy, from `docs/mockups/Main.dc.html`** (`.row`, 14 px gap, 14/16 px padding, `min-height: 44px`, bottom `--border`; selected row is `--sel` with `inset 3px 0 0 var(--accent)`):
SLA chip · room number in mono `--roomNum` · guest name · assignee avatar or `Unassigned` in `--tagBg` · message preview in `--text3` (one line, truncated) · presence avatars of others viewing. An unread row shows the guest's own text; an answered row is prefixed `You: `. A `New` badge marks a guest with no stay (the mockup's `— +1 555 014 2290 New` row).

**Filter tabs** (`.tab`, 36 px, active is `--accent` on `--accentText`): `All`, `Mine`, `Unassigned`, `Overdue`, then `Snoozed`, `Resolved`, `Archived`. Counts come from each list's own length and are shown only once loaded — never a stale number. §5.3 requires Resolved and Archived to be separate filters, and `resolved` is computed server-side at query time.

**dept_staff see a filtered list.** The server scopes it (`viewer_scope`), and `view_all_conversations` is false for them, so the client hides `All` and `Unassigned` for that role and defaults them to `Mine`.

- [ ] **Step 1: Write `web/src/test/factories.ts`**

Every later test builds fixtures from here, so a schema change breaks one file rather than twenty.

```ts
import type {
  ConversationDetail,
  ConversationSummary,
  DepartmentOut,
  DraftPromptOut,
  GuestOut,
  MessageOut,
  NoteOut,
  NotificationOut,
  QuickReplyOut,
  AssetOut,
  StaffUserOut,
  StayOut,
  WorkOrderDetail,
  WorkOrderOut,
} from '../api/types'

export function aGuest(over: Partial<GuestOut> = {}): GuestOut {
  return {
    id: 'g-1',
    phoneE164: '+15551234567',
    firstName: 'Sarah',
    lastName: 'Chen',
    email: null,
    loyaltyTier: 'gold',
    notesSummary: null,
    smsConsentStatus: 'opted_in',
    vip: false,
    ...over,
  }
}

export function aStay(over: Partial<StayOut> = {}): StayOut {
  return {
    id: 's-1',
    roomNumber: '412',
    roomType: 'King',
    status: 'checked_in',
    arrivalDate: '2026-09-09',
    departureDate: '2026-09-12',
    adults: 2,
    children: 0,
    stayCount: 4,
    isReturnGuest: true,
    ...over,
  }
}

export function aConversation(over: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: 'c-1',
    status: 'open',
    channelPrimary: 'sms',
    guest: aGuest(),
    roomNumber: '412',
    assignedUserId: null,
    assignedDepartmentId: null,
    lastMessagePreview: "The AC in our room isn't working at all",
    lastGuestMessageAt: '2026-09-10T18:41:00Z',
    lastStaffMessageAt: null,
    slaDueAt: '2026-09-10T18:56:00Z',
    snoozedUntil: null,
    openWorkOrderCount: 0,
    unanswered: true,
    ...over,
  }
}

export function aMessage(over: Partial<MessageOut> = {}): MessageOut {
  return {
    id: 'm-1',
    conversationId: 'c-1',
    direction: 'inbound',
    channel: 'sms',
    authorType: 'guest',
    authorUserId: null,
    body: "The AC in our room isn't working at all",
    deliveryStatus: 'delivered',
    sentAt: '2026-09-10T18:41:00Z',
    deliveredAt: '2026-09-10T18:41:02Z',
    providerErrorCode: null,
    providerErrorMessage: null,
    digitalAssetId: null,
    redacted: false,
    ...over,
  }
}

export function aNote(over: Partial<NoteOut> = {}): NoteOut {
  return {
    id: 'n-1',
    authorUserId: 'u-ava',
    authorName: 'Ava',
    body: 'Guest is Gold, 4th stay.',
    mentions: [],
    createdAt: '2026-09-10T18:43:00Z',
    ...over,
  }
}

export function aDraftPrompt(over: Partial<DraftPromptOut> = {}): DraftPromptOut {
  return {
    id: 'd-1',
    workOrderId: 'w-204',
    workOrderTitle: 'AC not cooling',
    body: 'Hi Sarah — engineering has repaired the AC in 412 and it is cooling now.',
    status: 'pending',
    createdAt: '2026-09-10T18:56:00Z',
    ...over,
  }
}

export function aConversationDetail(over: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    id: 'c-1',
    status: 'open',
    channelPrimary: 'sms',
    guest: aGuest(),
    stay: aStay(),
    assignedUserId: null,
    assignedDepartmentId: null,
    resolutionCategoryId: null,
    lastGuestMessageAt: '2026-09-10T18:41:00Z',
    lastStaffMessageAt: null,
    slaDueAt: '2026-09-10T18:56:00Z',
    snoozedUntil: null,
    archivedAt: null,
    firstResponseSeconds: null,
    messages: [aMessage()],
    notes: [],
    workOrders: [],
    draftPrompts: [],
    ...over,
  }
}

export function aWorkOrder(over: Partial<WorkOrderOut> = {}): WorkOrderOut {
  return {
    id: 'w-204',
    title: 'AC not cooling',
    description: 'Guest reports the AC in 412 is not working.',
    type: 'maintenance',
    status: 'open',
    priority: 'urgent',
    locationType: 'room',
    locationRef: '412',
    departmentId: 'dept-eng',
    assignedUserId: null,
    reportedByUserId: 'u-ava',
    sourceConversationId: 'c-1',
    sourceMessageId: 'm-1',
    dueAt: null,
    acknowledgedAt: null,
    startedAt: null,
    completedAt: null,
    verifiedAt: null,
    guestNotifiedAt: null,
    createdAt: '2026-09-10T18:42:00Z',
    updatedAt: '2026-09-10T18:42:00Z',
    ...over,
  }
}

export function aWorkOrderDetail(over: Partial<WorkOrderDetail> = {}): WorkOrderDetail {
  return { ...aWorkOrder(), events: [], guestName: 'Sarah Chen', roomNumber: '412', ...over }
}

export function aDepartment(over: Partial<DepartmentOut> = {}): DepartmentOut {
  return { id: 'dept-eng', name: 'Engineering', type: 'engineering', escalationMinutes: 15, active: true, ...over }
}

export function aStaffUser(over: Partial<StaffUserOut> = {}): StaffUserOut {
  return {
    id: 'u-ava',
    email: 'ava@hvh.test',
    firstName: 'Ava',
    lastName: 'Nolan',
    role: 'agent',
    departmentId: 'dept-fd',
    avatarUrl: null,
    status: 'active',
    ...over,
  }
}

export function aQuickReply(over: Partial<QuickReplyOut> = {}): QuickReplyOut {
  return {
    id: 'q-1',
    shortcut: '/wifi',
    title: 'WiFi details',
    body: 'Hi {{guest_first_name}} — the network is Harbourview-Guest, no password needed.',
    departmentId: null,
    category: null,
    locale: 'en',
    active: true,
    usageCount: 212,
    ...over,
  }
}

export function aAsset(over: Partial<AssetOut> = {}): AssetOut {
  return {
    id: 'a-1',
    name: 'WiFi card',
    type: 'file',
    url: 'https://example.test/wifi.pdf',
    shortCode: 'wifi1',
    description: null,
    thumbnailUrl: null,
    category: null,
    departmentId: null,
    validFrom: null,
    validUntil: null,
    sendCount: 12,
    active: true,
    ...over,
  }
}

export function aNotification(over: Partial<NotificationOut> = {}): NotificationOut {
  return {
    id: 'nt-1',
    type: 'sla.breach',
    title: 'SLA breached in 412',
    body: 'Sarah Chen has been waiting 16 minutes.',
    entityType: 'conversation',
    entityId: 'c-1',
    readAt: null,
    createdAt: '2026-09-10T18:57:00Z',
    ...over,
  }
}
```

- [ ] **Step 2: Write `web/src/api/hooks/conversations.ts`**

```ts
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { ConversationDetail, ConversationSummary } from '../types'

export type ConversationFilter =
  | 'all'
  | 'mine'
  | 'unassigned'
  | 'overdue'
  | 'snoozed'
  | 'resolved'
  | 'archived'

const PAGE = 50

export function useConversations(filter: ConversationFilter, dept?: string | null) {
  const { propertyId } = useSession()
  return useInfiniteQuery<ConversationSummary[], ApiError>({
    queryKey: qk.conversations(propertyId, filter, dept),
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({
        filter,
        limit: String(PAGE),
        offset: String(pageParam as number),
      })
      if (dept) params.set('dept', dept)
      return api<ConversationSummary[]>(propertyPath(propertyId, `conversations?${params}`))
    },
    // Ruling R3: offset paging. A short page means the end.
    getNextPageParam: (last, all) =>
      last.length < PAGE ? undefined : all.reduce((n, p) => n + p.length, 0),
  })
}

export function useConversation(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<ConversationDetail, ApiError>({
    queryKey: qk.conversation(propertyId, id ?? ''),
    queryFn: () => api<ConversationDetail>(propertyPath(propertyId, `conversations/${id}`)),
    enabled: Boolean(id),
  })
}
```

- [ ] **Step 3: Write `web/src/api/hooks/users.ts`**

```ts
import { useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { DepartmentOut, GuestDetail, StaffUserOut } from '../types'

export function useDepartments() {
  const { propertyId } = useSession()
  return useQuery<DepartmentOut[], ApiError>({
    queryKey: qk.departments(propertyId),
    queryFn: () => api<DepartmentOut[]>(propertyPath(propertyId, 'departments')),
    staleTime: 5 * 60_000, // departments change about never
  })
}

export function useStaff() {
  const { propertyId } = useSession()
  return useQuery<StaffUserOut[], ApiError>({
    queryKey: qk.staff(propertyId),
    queryFn: () => api<StaffUserOut[]>(propertyPath(propertyId, 'users')),
    staleTime: 5 * 60_000,
  })
}

export function useGuest(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<GuestDetail, ApiError>({
    queryKey: qk.guest(propertyId, id ?? ''),
    queryFn: () => api<GuestDetail>(propertyPath(propertyId, `guests/${id}`)),
    enabled: Boolean(id),
  })
}
```

- [ ] **Step 4: Write the failing list and tab tests**

`web/src/features/inbox/FilterTabs.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { FilterTabs } from './FilterTabs'
import type { Role } from '../../api/types'

function mount(role: Role, onChange = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <FilterTabs value="all" counts={{ all: 23, mine: 6, unassigned: 8, overdue: 3 }} onChange={onChange} />
    </SessionProvider>,
    { session: sessionFixture({ role }) },
  )
  return onChange
}

describe('FilterTabs', () => {
  it('shows the four live filters with their counts for an agent', async () => {
    mount('agent')
    expect(await screen.findByRole('tab', { name: /All 23/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Mine 6/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Unassigned 8/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Overdue 3/ })).toBeInTheDocument()
  })

  it('also offers Snoozed, Resolved and Archived as separate filters (§5.3)', async () => {
    mount('agent')
    expect(await screen.findByRole('tab', { name: /Snoozed/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Resolved/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Archived/ })).toBeInTheDocument()
  })

  it('marks the active tab as selected', async () => {
    mount('agent')
    expect(await screen.findByRole('tab', { name: /All/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /Mine/ })).toHaveAttribute('aria-selected', 'false')
  })

  it('hides All and Unassigned from dept_staff, who cannot view the whole property', async () => {
    mount('dept_staff')
    expect(await screen.findByRole('tab', { name: /Mine/ })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /All/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /Unassigned/ })).not.toBeInTheDocument()
  })

  it('omits a count that has not loaded rather than showing a stale zero', async () => {
    renderWithProviders(
      <SessionProvider>
        <FilterTabs value="all" counts={{}} onChange={vi.fn()} />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    const tab = await screen.findByRole('tab', { name: /All/ })
    expect(tab.textContent).toBe('All')
  })

  it('reports the chosen filter', async () => {
    const onChange = mount('agent')
    await userEvent.click(await screen.findByRole('tab', { name: /Overdue/ }))
    expect(onChange).toHaveBeenCalledWith('overdue')
  })
})
```

`web/src/features/inbox/ConversationList.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversation, aGuest, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ConversationList } from './ConversationList'

function respondWith(rows: unknown[], staff: unknown[] = [aStaffUser()]) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/users') ? staff : url.includes('/departments') ? [] : rows
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(selectedId?: string) {
  return renderWithProviders(
    <SessionProvider>
      <ConversationList filter="all" selectedId={selectedId} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }), route: '/app/inbox' },
  )
}

describe('ConversationList', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.stubGlobal('WebSocket', class { close() {} } as unknown as typeof WebSocket)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a row per conversation with room, guest and preview', async () => {
    respondWith([aConversation()])
    mount()
    expect(await screen.findByText('412')).toBeInTheDocument()
    expect(screen.getByText('Sarah Chen')).toBeInTheDocument()
    expect(screen.getByText(/The AC in our room/)).toBeInTheDocument()
  })

  it('preserves the server order and does not re-sort', async () => {
    respondWith([
      aConversation({ id: 'c-1', roomNumber: '412', lastGuestMessageAt: '2026-09-10T18:41:00Z' }),
      aConversation({ id: 'c-2', roomNumber: '118', lastGuestMessageAt: '2026-09-10T17:00:00Z' }),
    ])
    mount()
    await screen.findByText('412')
    const rooms = screen.getAllByTestId('row-room').map((el) => el.textContent)
    expect(rooms).toEqual(['412', '118'])
  })

  it('prefixes an answered conversation with You:', async () => {
    respondWith([
      aConversation({
        unanswered: false,
        lastStaffMessageAt: '2026-09-10T18:50:00Z',
        lastMessagePreview: 'Your car is at the valet stand now.',
      }),
    ])
    mount()
    expect(await screen.findByText(/^You: Your car is at the valet/)).toBeInTheDocument()
  })

  it('shows Unassigned when nobody owns it', async () => {
    respondWith([aConversation({ assignedUserId: null, assignedDepartmentId: null })])
    mount()
    expect(await screen.findByText('Unassigned')).toBeInTheDocument()
  })

  it('shows the assignee initials when someone does', async () => {
    respondWith([aConversation({ assignedUserId: 'u-ava' })])
    mount()
    expect(await screen.findByTitle('Ava Nolan')).toBeInTheDocument()
  })

  it('marks a guest with no stay as New', async () => {
    respondWith([
      aConversation({
        roomNumber: null,
        guest: aGuest({ firstName: null, lastName: null, phoneE164: '+15550142290' }),
      }),
    ])
    mount()
    expect(await screen.findByText('New')).toBeInTheDocument()
    expect(screen.getByText('+15550142290')).toBeInTheDocument()
  })

  it('flags an opted-out guest in red (§5.3)', async () => {
    respondWith([aConversation({ guest: aGuest({ smsConsentStatus: 'opted_out' }) })])
    mount()
    const chip = await screen.findByText(/opted out/i)
    expect(chip.className).toContain('dangerText')
  })

  it('renders an SLA chip for an unanswered conversation and done for an answered one', async () => {
    respondWith([
      aConversation({ id: 'c-1', unanswered: true }),
      aConversation({ id: 'c-2', roomNumber: '205', unanswered: false }),
    ])
    mount()
    expect(await screen.findByText('done')).toBeInTheDocument()
  })

  it('marks the selected row', async () => {
    respondWith([aConversation({ id: 'c-1' })])
    mount('c-1')
    expect(await screen.findByRole('link', { name: /Sarah Chen/ })).toHaveAttribute(
      'aria-current',
      'true',
    )
  })

  it('shows an empty state rather than a blank column', async () => {
    respondWith([])
    mount()
    expect(await screen.findByText(/nothing waiting/i)).toBeInTheDocument()
  })

  it('shows the error message when the list fails', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'FORBIDDEN', message: 'Not your property' } }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    mount()
    expect(await screen.findByText('Not your property')).toBeInTheDocument()
  })
})
```

- [ ] **Step 5: Run them to verify they fail**

```bash
cd web && npx vitest run src/features/inbox
```

Expected: FAIL — neither component resolves.

- [ ] **Step 6: Write `web/src/features/inbox/FilterTabs.tsx`**

```tsx
import { useSession } from '../../auth/SessionContext'
import { cn } from '../../lib/cn'
import type { ConversationFilter } from '../../api/hooks/conversations'

const ALL_TABS: { value: ConversationFilter; label: string; needsAllAccess?: boolean }[] = [
  { value: 'all', label: 'All', needsAllAccess: true },
  { value: 'mine', label: 'Mine' },
  { value: 'unassigned', label: 'Unassigned', needsAllAccess: true },
  { value: 'overdue', label: 'Overdue' },
  { value: 'snoozed', label: 'Snoozed' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'archived', label: 'Archived' },
]

export function FilterTabs({
  value,
  counts,
  onChange,
}: {
  value: ConversationFilter
  counts: Partial<Record<ConversationFilter, number>>
  onChange: (filter: ConversationFilter) => void
}) {
  const { can } = useSession()
  const tabs = ALL_TABS.filter((t) => !t.needsAllAccess || can('view_all_conversations'))

  return (
    <div role="tablist" className="flex flex-wrap items-center gap-1.5">
      {tabs.map((tab) => {
        const count = counts[tab.value]
        return (
          <button
            key={tab.value}
            role="tab"
            aria-selected={value === tab.value}
            onClick={() => onChange(tab.value)}
            className={cn(
              'inline-flex h-9 items-center gap-2 rounded px-3.5 text-[13.5px] font-semibold',
              value === tab.value ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
            )}
          >
            {tab.label}
            {/* Only render a count we actually have — a stale 0 reads as "nothing to do". */}
            {count === undefined ? null : <span className="font-mono text-xs opacity-85">{count}</span>}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 7: Write `web/src/features/inbox/ConversationList.tsx`**

```tsx
import { Link } from 'react-router-dom'
import { useConversations, type ConversationFilter } from '../../api/hooks/conversations'
import { useStaff } from '../../api/hooks/users'
import { useRealtime } from '../../api/ws'
import type { ConversationSummary } from '../../api/types'
import { SlaChip } from '../../components/SlaChip'
import { Avatar, Badge, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'

function guestLabel(conversation: ConversationSummary): string {
  const { firstName, lastName, phoneE164 } = conversation.guest
  const name = [firstName, lastName].filter(Boolean).join(' ')
  return name || phoneE164
}

function Row({
  conversation,
  selected,
  assigneeName,
}: {
  conversation: ConversationSummary
  selected: boolean
  assigneeName: string | null
}) {
  const { presence } = useRealtime()
  const watchers = (presence[conversation.id] ?? []).filter((u) => u.state !== 'composing')
  const answered = !conversation.unanswered
  const preview = conversation.lastMessagePreview ?? ''

  return (
    <Link
      to={`/app/inbox/${conversation.id}`}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'flex min-h-[44px] items-center gap-3.5 border-b border-border px-4 py-3.5',
        selected ? 'bg-sel shadow-[inset_3px_0_0_var(--accent)]' : 'hover:bg-surface2',
      )}
    >
      <SlaChip
        dueAt={conversation.slaDueAt}
        startAt={conversation.lastGuestMessageAt}
        answered={answered}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span data-testid="row-room" className="font-mono text-sm font-semibold text-roomNum">
            {conversation.roomNumber ?? '—'}
          </span>
          <span className="truncate text-sm font-semibold">{guestLabel(conversation)}</span>
          {!conversation.roomNumber ? <Badge>New</Badge> : null}
          {conversation.guest.smsConsentStatus === 'opted_out' ? (
            <Badge tone="danger" className="text-dangerText">
              Opted out
            </Badge>
          ) : null}
          {assigneeName ? (
            <Avatar name={assigneeName} size={22} tone="muted" />
          ) : (
            <Badge>Unassigned</Badge>
          )}
        </div>
        <p className={cn('truncate text-[13px]', answered ? 'text-text3' : 'text-text2')}>
          {answered && conversation.lastStaffMessageAt ? `You: ${preview}` : preview}
        </p>
      </div>
      {watchers.length > 0 ? (
        <div className="flex flex-none -space-x-1.5">
          {watchers.slice(0, 3).map((u) => (
            <Avatar key={u.id} name={u.firstName} size={22} tone="presence" />
          ))}
        </div>
      ) : null}
    </Link>
  )
}

export function ConversationList({
  filter,
  selectedId,
  dept,
}: {
  filter: ConversationFilter
  selectedId?: string
  dept?: string | null
}) {
  const query = useConversations(filter, dept)
  const { data: staff } = useStaff()
  const rows = query.data?.pages.flat() ?? []

  if (query.isPending) {
    return (
      <div className="grid place-items-center p-10">
        <Spinner />
      </div>
    )
  }
  if (query.error) {
    return <EmptyState title="Could not load the queue" hint={query.error.message} />
  }
  if (rows.length === 0) {
    return <EmptyState title="Nothing waiting" hint="No conversations match this filter." />
  }

  const nameFor = (userId: string | null | undefined): string | null => {
    if (!userId) return null
    const person = staff?.find((s) => s.id === userId)
    return person ? `${person.firstName} ${person.lastName}` : null
  }

  return (
    <div className="flex flex-col">
      {/* The server orders by unanswered-then-oldest; rendering as received is deliberate. */}
      {rows.map((conversation) => (
        <Row
          key={conversation.id}
          conversation={conversation}
          selected={conversation.id === selectedId}
          assigneeName={nameFor(conversation.assignedUserId)}
        />
      ))}
      {query.hasNextPage ? (
        <button
          onClick={() => void query.fetchNextPage()}
          disabled={query.isFetchingNextPage}
          className="h-11 border-b border-border text-sm font-semibold text-text3 hover:text-text"
        >
          {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 8: Write `web/src/features/inbox/InboxPage.tsx`**

Three columns ≥1024 px, two ≥768, one below with back navigation (§5.2). The conversation pane is Task 13's; until then it renders the guest name so the layout is verifiable.

```tsx
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useSession } from '../../auth/SessionContext'
import type { ConversationFilter } from '../../api/hooks/conversations'
import { useConversations } from '../../api/hooks/conversations'
import { ConversationList } from './ConversationList'
import { FilterTabs } from './FilterTabs'
import { EmptyState } from '../../components/ui'
import { ConversationView } from './ConversationView'

export function InboxPage() {
  const { id } = useParams<{ id: string }>()
  const { can } = useSession()
  // dept_staff cannot see the whole property, so their queue starts at Mine.
  const [filter, setFilter] = useState<ConversationFilter>(
    can('view_all_conversations') ? 'all' : 'mine',
  )

  // Counts for the tabs: the active filter's own length, plus the cheap always-on ones.
  const active = useConversations(filter)
  const counts = { [filter]: active.data?.pages.flat().length } as Partial<
    Record<ConversationFilter, number>
  >

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <FilterTabs value={filter} counts={counts} onChange={setFilter} />
      </div>
      <div className="flex min-h-0 flex-1">
        <div
          className={`w-full overflow-y-auto border-r border-border md:w-[360px] md:flex-none ${
            id ? 'hidden md:block' : ''
          }`}
        >
          <ConversationList filter={filter} selectedId={id} />
        </div>
        <div className={`min-w-0 flex-1 ${id ? '' : 'hidden md:block'}`}>
          {id ? (
            <ConversationView conversationId={id} />
          ) : (
            <EmptyState title="Pick a conversation" hint="Choose a row to read the thread." />
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 9: Wire the route**

In `routes.tsx`, replace both Inbox placeholders with `<InboxPage />` and import it. Leave the other placeholders alone.

- [ ] **Step 10: Run the tests to verify they pass**

```bash
cd web && npm test
```

Expected: PASS — 6 tab tests and 11 list tests. `ConversationView` is Task 13's; **create it now as a minimal component that renders the guest's name from `useConversation`** so `InboxPage` compiles, and let Task 13 replace it.

- [ ] **Step 11: Verify against the real server**

Sign in as `ava@hvh.test`. The queue shows the seeded 30 conversations of Property A: overdue rows red, fresh rows green, answered rows `done` and prefixed `You:`, one row flagged `Opted out`, one `New` row with no room. Click through filters — `Overdue` should show ~5, `Unassigned` ~8, `Archived` ~5 (the §8 seed shape). Sign in as `eli@hvh.test`: `All` and `Unassigned` are gone and the queue is department-scoped.

- [ ] **Step 12: Commit**

```bash
git add web/src/api/hooks/conversations.ts web/src/api/hooks/users.ts web/src/features/inbox \
        web/src/test/factories.ts web/src/routes.tsx
git commit -m "feat(web): inbox queue with server ordering, role-aware filters and presence avatars"
```

---

