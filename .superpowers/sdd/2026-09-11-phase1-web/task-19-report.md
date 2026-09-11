# Task 19: Admin CRUD — Report

## What I implemented

Following the brief exactly (section list, column sets, and the three given test files are
literal), plus one additional regression test the dispatch explicitly required:

- **`web/src/api/queryKeys.ts`** — added `quickRepliesAll`, `assetsAll`, `categoriesAll`,
  `staffAll` prefix helpers.
- **`web/src/api/hooks/content.ts`** — added the shared `useWrite<TBody, TResult>` factory and
  `useCreateQuickReply`/`usePatchQuickReply`/`useDeleteQuickReply`,
  `useCreateAsset`/`usePatchAsset`/`useDeleteAsset`,
  `useCreateCategory`/`usePatchCategory`/`useDeleteCategory` — **all invalidating the `*All`
  prefix key**, not the exact (search-suffixed) key.
- **`web/src/api/hooks/users.ts`** — added `useCreateStaff`, `usePatchStaff`, `useDeleteStaff`,
  invalidating `qk.staffAll`.
- **`web/src/features/admin/AdminTable.tsx`**, **`EditPanel.tsx`** — generic, resource-agnostic,
  as given in the brief verbatim.
- **`web/src/features/admin/QuickRepliesAdmin.tsx`** — as given, with two corrections (see
  Self-review).
- **`web/src/features/admin/UsersAdmin.tsx`**, **`AssetsAdmin.tsx`**, **`CategoriesAdmin.tsx`** —
  written to the same table+edit-panel pattern, columns/fields exactly per the brief's table.
  `CategoriesAdmin` flattens the server's nested `CategoryOut[]` tree into rows carrying `depth`
  and `parentName` for the "Name (indented by depth) · Parent · Active" column set.
- **`web/src/features/admin/AdminPage.tsx`** — sub-nav with the four live sections as links and
  the five Phase 2 sections (`Departments`, `Property settings`, `Automations`, `Blocked
  numbers`, `Integrations`) rendered as disabled, non-link rows under "Greyed items arrive in
  Phase 2", plus the nested `/users`, `/quick-replies`, `/assets`, `/categories` routes and an
  index redirect to `users`.
- **`web/src/routes.tsx`** — wired `<AdminPage />` into the existing `manage_admin`-gated
  `admin/*` route, removing the now-dead `Placeholder` helper (its only remaining call site).

## What I tested and the results

`npx vitest run src/features/admin` — 21/21 passing (12 quick-reply incl. my added invalidation
test, 5 user, 4 admin-page). Full suite `npx vitest run` — **344/344 passing, 42/42 files**, zero
`act()` warnings, zero unhandled rejections anywhere in the run (checked with a grep for
`warning|not wrapped in act|unhandled` across full output — no hits).

`npx tsc -b` — clean, no output.

## TDD evidence

**RED** — `npx vitest run src/features/admin` before any implementation file existed:
```
Error: Failed to resolve import "./AdminPage" from "src/features/admin/AdminPage.test.tsx"...
Error: Failed to resolve import "./QuickRepliesAdmin" from ".../QuickRepliesAdmin.test.tsx"...
Error: Failed to resolve import "./UsersAdmin" from ".../UsersAdmin.test.tsx"...
Test Files  3 failed (3)
     Tests  no tests
```
Expected: the three feature modules didn't exist yet.

**GREEN** — after implementing all components/hooks:
```
✓ src/features/admin/AdminPage.test.tsx (4 tests)
✓ src/features/admin/UsersAdmin.test.tsx (5 tests)
✓ src/features/admin/QuickRepliesAdmin.test.tsx (12 tests)
Test Files  3 passed (3)
     Tests  21 passed (21)
```

## The invalidation proof

Added a 12th test to `QuickRepliesAdmin.test.tsx` (beyond the brief's literal 11), per the
dispatch's explicit instruction to prove the fix with a test:

```ts
it('refreshes a search-filtered list after an edit made under that filter', async () => {
  mount()
  await screen.findByText('/wifi')
  await userEvent.type(screen.getByPlaceholderText(/search/i), 'shuttle')
  await waitFor(() =>
    expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('q=shuttle'))).toBe(true),
  )
  const filteredGets = () =>
    vi.mocked(fetch).mock.calls.filter(
      ([u, i]) => (!i || !i.method || i.method === 'GET') && String(u).includes('q=shuttle'),
    ).length
  const before = filteredGets()

  await userEvent.click(await screen.findByText('WiFi details'))
  const title = await screen.findByLabelText('Title')
  await userEvent.clear(title)
  await userEvent.type(title, 'WiFi info')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))

  await waitFor(() => expect(filteredGets()).toBeGreaterThan(before))
})
```

**Verified this test actually catches the bug** — I temporarily reverted the three quick-reply
mutation invalidation keys from `qk.quickRepliesAll(p)` back to the buggy `qk.quickReplies(p)`
(exact key, `q: ''`) and re-ran just this test:
```
× QuickRepliesAdmin > refreshes a search-filtered list after an edit made under that filter
  → expect(filteredGets()).toBeGreaterThan(before)
  Test Files  1 failed (1)
```
Failed as expected — with the exact key, the still-mounted filtered query (`['quickReplies',
propertyId, 'shuttle']`) never gets invalidated by a save, so no refetch occurs. Restored the
`*All` fix and re-ran: passes (12/12 in the file).

**Live admin→composer-palette check — I did run this, via Playwright browser automation**
(`mcp__plugin_playwright_playwright__*`, available in this session). Server was already running
on :5000/:5173 (as the dispatch warned). Steps:

1. Logged out the pre-existing Morgan Manager session (`POST /api/auth/logout` via
   `browser_evaluate`, since no logout control exists in the UI yet), signed in as
   `alex@hvh.test` / `Password123!`.
2. Visited `/app/admin/quick-replies` — table renders all 15 real quick replies correctly
   (shortcut/title/body/dept/uses/active), matching the mockup layout exactly.
3. **First attempt at editing `/wifi`'s body and saving failed against the real server** with
   "Invalid request body" — a genuine defect (see below), not a test artifact.
4. After fixing it, edited `/wifi`'s body to a distinguishable marker string and saved — table
   updated immediately, panel closed, no console errors.
5. **The actual cross-route proof**: navigated via in-app `NavLink` clicks (not full page
   reloads, so the same `QueryClient` instance persisted) — Admin → Quick replies, edited `/wifi`
   again to a second marker ("ROUND-TWO"), saved, then clicked Inbox → opened a conversation →
   typed `/wifi` in the composer. **The `/` palette showed "ROUND-TWO" immediately** — the
   composer's `useQuickReplies()` query (key `['quickReplies', propertyId, '']`) had never been
   fetched fresh in this session before that moment on this specific route visit, so this is a
   real, live confirmation of prefix invalidation reaching a differently-keyed active/inactive
   query across a route change, not just server truth on reload.
6. Verified the full create → delete lifecycle for real: created `/e2etest`, saw it appear in the
   table (16 active), clicked it, clicked Delete → inline "Delete this? This cannot be undone."
   appeared in place of the button (no DELETE fired yet) → clicked Confirm → row disappeared,
   count back to 15 active. No console errors throughout.
7. Spot-checked `Digital assets` and `Resolution categories` — both render real server data
   correctly; categories show the flattened parent/child tree (e.g. "Electrical" → parent
   "Maintenance") as designed.
8. Restored `/wifi`'s body to its original text afterward, to leave the dev database clean.

**A real defect this live check caught, that the mocked unit tests could not**: the server's
`QuickReplyPatch` Pydantic model (`server/app/schemas/content.py`) has no `locale` field, and
`CamelModel`'s `model_config` sets `extra="forbid"` (`server/app/schemas/common.py`) — so any
PATCH carrying `locale` is rejected with a 400. My `save()` (following the brief's literal
`patch.mutate(draft, ...)`, which sends the whole `Draft` including `locale`) hit this instantly
against the real server, while every mocked test passed cleanly because the test double doesn't
validate schema. Fixed by building an explicit PATCH payload for quick replies that excludes
`locale` (create still sends it — `QuickReplyIn` does accept `locale`). Verified `AssetPatch`/
`CategoryPatch` don't have the same issue (their fields are a strict superset match of what
`AssetsAdmin`/`CategoriesAdmin`'s `Draft`s send). Re-ran the full test suite after this fix — no
regressions (344/344 still pass) — and re-verified the live edit succeeds end-to-end per step 4
above.

## `npx tsc -b`

Clean, no output, no warnings.

## Files changed

New:
- `web/src/features/admin/AdminTable.tsx`
- `web/src/features/admin/EditPanel.tsx`
- `web/src/features/admin/QuickRepliesAdmin.tsx`
- `web/src/features/admin/QuickRepliesAdmin.test.tsx`
- `web/src/features/admin/UsersAdmin.tsx`
- `web/src/features/admin/UsersAdmin.test.tsx`
- `web/src/features/admin/AssetsAdmin.tsx`
- `web/src/features/admin/CategoriesAdmin.tsx`
- `web/src/features/admin/AdminPage.tsx`
- `web/src/features/admin/AdminPage.test.tsx`

Modified:
- `web/src/api/queryKeys.ts`
- `web/src/api/hooks/content.ts`
- `web/src/api/hooks/users.ts`
- `web/src/routes.tsx`
- `web/src/features/login/LoginPage.tsx` (out-of-brief defect fix, see below)
- `web/src/routes.test.tsx` (out-of-brief test-mock fix, see below)

## Self-review findings

**Defects found in the brief's literal code (fixed, not worked around):**

1. **`UsersAdmin.test.tsx` imported `waitFor` but never used it** — an unused import, which
   fails under this project's `noUnusedLocals: true`. Removed the import; no assertion was
   touched.
2. **Factory-default collision in `UsersAdmin.test.tsx`'s `STAFF` fixture** — `aStaffUser({id:
   'u-eli', ...})` didn't override `email`, so it silently inherited the factory's default
   `'ava@hvh.test'` — the same email as the other fixture row. `screen.getByText('ava@hvh.test')`
   then failed with "multiple elements found." This is exactly the "factory defaults surprising a
   test" failure mode called out in the dispatch. Fixed by giving Eli's fixture its own email
   (`eli@hvh.test`); no assertion changed, only the input data.
3. **`AdminPage.tsx`'s relative `NavLink to="users"` (etc.) doesn't resolve correctly** under
   this project's `v7_relativeSplatPath` router future flag (set in the test harness's
   `MemoryRouter`, and matching how the real app mounts `AdminPage` at the `admin/*` splat under
   `routes.tsx`). Confirmed via instrumentation that a relative `to="users"` resolved to
   `/app/admin/users/users` (or similar, sibling-appended) instead of `/app/admin/users`, so the
   link never carried `aria-current="page"` even when it was the active section — failing the
   brief's own `AdminPage.test.tsx` ("marks the current section", "redirects a bare /app/admin
   to users"). Fixed by giving the four `LIVE` nav entries absolute `to` paths
   (`/app/admin/users`, etc.) instead of relative ones — simpler than relative resolution and
   correct regardless of splat-flag semantics, in both the test harness and the real app. The
   nested `<Route index element={<Navigate to="users" replace />}>` inside `AdminPage`'s own
   `<Routes>` did **not** need the same fix — it sits in a properly nested routing context, not
   the outer splat, and resolved correctly as given.
4. **`QuickRepliesAdmin.tsx`'s `open()`** assigned `reply.departmentId`/`reply.category` directly
   into `Draft` fields typed `string | null`, but `QuickReplyOut.departmentId`/`.category` are
   optional properties (`string | null | undefined`), which `tsc -b` correctly rejected. Fixed
   with `?? null` coalescing on both, matching the pattern already used in `AssetsAdmin.open()`.
   No behavior change for real API responses (which always populate these fields with a value or
   `null`).
5. **`QuickRepliesAdmin.tsx`'s `save()` sent the whole `Draft` (including `locale`) on PATCH** —
   invisible to every mocked unit test but rejected outright by the real server (400 "Invalid
   request body"), since `QuickReplyPatch` has no `locale` field and the server's `CamelModel`
   forbids unknown fields. Only found by driving the real app in a browser (see the live
   verification section above). Fixed by sending an explicit patch payload that excludes
   `locale`; create is unaffected since `QuickReplyIn` does accept it.

**One defect found and fixed that is genuinely out of this task's file list, and I want to flag
it explicitly rather than bury it:**

6. **`LoginPage.tsx` had a latent redirect-loop bug**, exposed (not created) by this task. Admin
   was previously the one `/app/*` screen with no real data fetching, so a session that goes bad
   while the user is on it never surfaced this. Once `UsersAdmin` does real `useStaff()` /
   `useDepartments()` fetches, a 401 from either trips `RequireAuth`'s `onUnauthorized` handler,
   which calls `refetch()` on the session query; if that also 401s (a genuinely dead session),
   `RequireAuth` correctly bounces to `/login` — but `LoginPage` checked only `session &&
   session.memberships.length > 0`, and react-query keeps the *last successful* `data` cached
   through a subsequent error. So `LoginPage` saw the stale-but-truthy session and immediately
   navigated back into the app, which `RequireAuth` immediately bounced back out again — an
   instant `/login` ⇄ `/app/admin/users` oscillation that hammered `/api/auth/me` in a tight loop
   and left `routes.test.tsx`'s `'lets an admin into admin'` test unable to find any stable DOM.
   I confirmed this with direct instrumentation (a scratch test dumping the fetch call log)
   before touching anything, then fixed it narrowly: `LoginPage` now gates on `isSuccess` (react
   query's "the *current* status is success" flag) in addition to `data`, so a session that has
   since errored is never treated as "still signed in." This is a real production bug — any user
   whose cookie expires while a real request is in flight on a page that previously never
   fetched anything would have hit this same flicker-loop — not just a test artifact, so I fixed
   it rather than only patching the test around it. I also extended `routes.test.tsx`'s blanket
   fetch mock to 200 the two new admin endpoints (`/users`, `/departments`) the same way
   `unread-count` was already special-cased, mirroring the file's existing pattern and comment
   style, since a genuinely-dead-session simulation isn't what any of these route tests are
   about. Both changes are minimal (a one-line predicate change plus one added mock branch) and
   the existing `routes.test.tsx` suite is the regression coverage — all 11 of its tests pass,
   including the previously-failing one.

**Quality checks:**
- Mutations invalidate the `*All` prefix key everywhere (verified by the invalidation-proof test
  above, and by reading every `useCreate*`/`usePatch*`/`useDelete*`).
- `usageCount` (quick replies) and `sendCount` (assets) are rendered only as read-only
  `EditPanel` subtitle text (`"{n} uses"` / `"{n} sends"`), never as an input field — confirmed
  by the brief's own test (`queryByLabelText(/uses/i)).not.toBeInTheDocument()`) and by reading
  the JSX (no field binds to either).
- Delete is the inline confirm (`EditPanel`'s built-in `confirming` state), never a stacked
  dialog; confirmed no `DELETE` fires until "Confirm" is clicked (brief's own test), and "Keep"
  backs out without firing anything.
- Edit panels seed once from `open(row)` into local `draft` state and are never re-seeded by an
  effect while open — draft state is plain `useState`, server state stays in TanStack Query only.
- `AdminTable`/`EditPanel` remain fully resource-agnostic — no resource-specific logic leaked
  into either.
- Phase 2 sections render as disabled `<li>` text, never as `<a>`/`<Link>`/`<NavLink>` — confirmed
  by the brief's own `queryByRole('link', ...)).not.toBeInTheDocument()` assertions.
- No `any`; the one type-safety wrinkle in the brief's example code (`useDeleteQuickReply`'s
  `Record<string, never>` body type paired with `remove.mutate({ id: draft.id } as never, ...)`)
  was avoided rather than reproduced: I gave the three `useDelete*` hooks a `{ id: string }` body
  type instead, and capture `draftId = draft?.id` as a plain local before the `onDelete`
  ternary so TS narrows it without a cast. No `as never`/`as any`/`@ts-ignore` anywhere in the
  new code.
- Only design-token color classes used throughout (`bg-surface2`, `text-text3`, `bg-sel`,
  `border-border2`, `text-dangerText`, etc.) — no hex, no stock Tailwind palette names, no bare
  `black`/`white`.
- Test output is pristine across the whole suite: no `act()` warnings, no unhandled rejections.

**Scope discipline:** `AssetsAdmin`/`CategoriesAdmin`/`UsersAdmin` have no search box — matching
that `useAssets()`, `useCategories()`, and `useStaff()` take no filter argument at all (unlike
`useQuickReplies(q)`), so there's no server-side filtering to wire up and adding a client-only
search input would be scope beyond what the brief's column/field table asks for. I did not add
active/inactive counts to the Assets/Categories/Users headers beyond what the brief's literal
`QuickRepliesAdmin` code showed, to avoid inventing UI the brief didn't ask for.

## Issues or concerns

- **Step 6's live verification was performed** (Playwright browser automation was available in
  this session) and is the reason two real defects (items 5 and 6 above) surfaced at all — both
  were invisible to the full mocked test suite. Not covered live: changing a user's role and
  confirming a second signed-in session's nav updates on next load (would need two concurrent
  browser sessions), and adding/using a category during archive (I did confirm the Categories
  screen itself renders and edits correctly, but didn't run it through `ArchiveDialog`). Given the
  `usePatchCategory`/`ArchiveDialog` integration is unchanged plumbing (categories were already
  consumed via `useCategories()` before this task), I judge this a low-risk gap, but it wasn't
  visually confirmed.
- The `LoginPage.tsx` / `routes.test.tsx` changes are outside this task's stated file list. I
  made the call to fix them because (a) it's a genuine, user-facing correctness bug that my
  in-scope change exposed, not created, (b) leaving it would have left the full test suite red,
  and (c) the fix is small, narrowly targeted, and well-covered by the existing (now-passing)
  `routes.test.tsx` suite. Flagging this prominently in case the reviewer wants it as a separate
  commit or wants to weigh in before it ships as part of Task 19.
- `eslint` has no config file in this repo (`ESLint couldn't find a configuration file`) — this
  is pre-existing and unrelated to this task; I did not attempt to fix it.
