# Task 18: Notifications — bell, unread count, centre

## What I implemented

- `web/src/api/hooks/notifications.ts` — `useNotifications(unreadOnly)`, `useUnreadCount()`,
  `useMarkRead()`, `useMarkAllRead()`, exactly as given in the brief's Step 1 (verbatim).
- `web/src/features/notifications/NotificationsPage.tsx` — the Alerts centre: All/Unread tabs,
  a "Mark all read" button (disabled when unread count is 0), a row list with an unread `bg-accent`
  dot, title/body/relative-time, `bg-sel` for unread rows. Opening a linkable row marks it read
  and navigates in one action (the `Link`'s `onClick` fires the mutation before/alongside
  navigation). Rows with no mappable `entityType`/`entityId` render as a plain `<div>`, no link.
  Verbatim from the brief's Step 3.
- `web/src/features/notifications/NotificationsPage.test.tsx` — the brief's Step 2 test file,
  verbatim.
- `web/src/AppLayout.tsx` — added a `Shell` component that calls `useUnreadCount()` and passes
  `unreadCount` into `AppShell`; `AppShell` itself is untouched (already had the prop from Task 9).
- `web/src/routes.tsx` — replaced the `Placeholder name="Alerts"` route with `<NotificationsPage />`.
- **Did not create `NotificationBell.tsx`** — per the task's explicit instruction and the brief's
  own "Implementer: if nothing mounts NotificationBell, do not create the file" note. Nothing in
  Phase 1 mounts it; the nav badge is the only affordance.

## What I tested and the results

### TDD evidence

**RED** — `cd web && npx vitest run src/features/notifications/NotificationsPage.test.tsx` before
`NotificationsPage.tsx` existed:

```
FAIL  src/features/notifications/NotificationsPage.test.tsx [ src/features/notifications/NotificationsPage.test.tsx ]
Error: Failed to resolve import "./NotificationsPage" from
"src/features/notifications/NotificationsPage.test.tsx". Does the file exist?
```

Expected failure — the module under test did not exist yet.

**GREEN** — same command after writing `NotificationsPage.tsx`:

```
✓ src/features/notifications/NotificationsPage.test.tsx (10 tests) 408ms

Test Files  1 passed (1)
     Tests  10 passed (10)
```

**Note on the brief's "11 notification tests" claim**: the brief's Step 5 says "Expected: PASS —
11 notification tests," but the literal test code in Step 2 contains exactly 10 `it()` blocks. I
counted them by hand (lists/body, unread-dot-shown, unread-dot-hidden-when-read, conversation
link, work-order link, unlinkable-plain-text, marks-read-on-open, mark-all-read, filter-to-unread,
empty-state = 10). This is a prose/code count mismatch in the brief, not a defect in the code —
reporting it per the standing instruction rather than inventing an 11th test to match the prose.

### Full suite

`cd web && npm test -- --run`:

```
Test Files  39 passed (39)
     Tests  323 passed (323)
```

No `act()` warnings, no unhandled rejections in the output.

### A real defect this task exposed in `routes.test.tsx` (not part of the brief's file list)

Wiring `useUnreadCount()` unconditionally into `AppLayout`'s new `Shell` (exactly as the brief's
Step 4 prescribes) means every `/app/*` route now fires one real fetch on mount — previously the
shell was fetch-free (Task 9), so nothing did. `routes.test.tsx`'s `beforeEach` stubs `fetch` to
return a blanket 401 for every request, on the documented assumption that role-seeded tests never
actually hit the network (session is pre-seeded into the query cache). That assumption held before
this task. After wiring `Shell`, the `/app/admin/users` route — which previously fetched nothing —
now fires `useUnreadCount()`'s request, gets the blanket 401, and that 401 trips
`RequireAuth`'s `onUnauthorized` handler (any 401 anywhere is treated as "the cookie died,"
by design), which refetches `/api/auth/me`, also 401s, and redirects to `/login` — racing with
`lets an admin into admin`'s `findByText('Admin')` assertion. I confirmed this was newly caused by
my change (not pre-existing) by stashing my changes and re-running `routes.test.tsx`: 11/11 passed
on `main`; re-applying my changes reproduced the failure deterministically (re-ran twice).

Fix: `routes.test.tsx`'s `beforeEach` mock now special-cases any URL containing `unread-count` to
return `{ count: 0 }` with status 200, and keeps 401ing everything else exactly as before —
preserving every existing test's intent (including the still-401 auth/me path the "unauthenticated
visitor" test depends on) while no longer racing the admin route. This is a test-scaffolding fix
only; no production code was weakened to make anything pass.

`cd web && npx vitest run src/routes.test.tsx` after the fix:

```
✓ src/routes.test.tsx (11 tests) 199ms
Test Files  1 passed (1)
     Tests  11 passed (11)
```

## Live verification (Step 6)

Ran the real server (`.venv\Scripts\python.exe server\dev_start.py`) and the real web dev server
(`npm run dev` in `web/`), then drove an actual browser via Playwright MCP tools (login form,
clicks, and DOM snapshots — no invented output).

**What the seeded data actually contained**: I read `server/seed/seed.py` end to end and confirmed
it never imports `app.domain.notifications` and never constructs a `Notification` row directly —
static seeding produces **zero** notifications for anyone, Ava included. Overdue conversations from
the seed script are deliberately pre-marked with a past `sla_breach_notified_at` (e.g. `c.sla_breach_notified_at
= at + timedelta(minutes=16)`) specifically so a fresh SLA sweep does *not* immediately re-fire on
startup. I did not assume this — I grepped for `Notification(` in seed.py (0 matches) and for the
domain functions it might call (none). This matches the brief's own warning to check rather than
assume the seed data's shape.

However, the *running* local dev database (`server/data/app.db`) was not a fresh seed — the launcher
printed "Database already has data, skipping seed," meaning it's the persistent dev DB accumulated
across many prior local sessions in this repo, with `START_WORKER=1` running the real `sla.sweep`
job every 30s the whole time. That live sweep had organically created **7 unread `sla.breach`**
notifications for Ava by the time I logged in (queried directly via `curl` against
`/api/p/<propertyId>/notifications` before touching the browser, to see ground truth first).

Checks run, each observed directly (not assumed):

1. **Nav badge shows a live count.** Logged in as `ava@hvh.test` / `Password123!`. Accessibility
   snapshot showed `link "Alerts 7"` in the nav.
2. **Opening the centre shows the rows, each linking into the inbox.** All 7 rows rendered as
   `<a href="/app/inbox/<conversationId>">`, e.g. `/app/inbox/a14f3309-8831-4b3b-afeb-0fe447e30f31`
   for "Response overdue: Chloe Tanaka · 402" — matching the seeded `entityType: 'conversation'`.
3. **Opening one marks it read and navigates — one action.** Clicked the Chloe Tanaka row; the
   browser navigated to `/app/inbox/a14f3309-…` (confirmed by page URL) and, without any reload,
   the nav badge dropped from "Alerts 7" to "Alerts 6" in the same snapshot. Returning to
   `/app/notifications` and switching to the "Unread" tab confirmed that row was excluded (6 rows,
   Chloe Tanaka gone).
4. **Mark all read empties the badge.** Clicked "Mark all read": the nav badge disappeared entirely
   (plain `link "Alerts"`, no count span — confirming `AppShell` only renders the badge element when
   `unreadCount` is truthy, per Task 9's contract), the "Mark all read" button became `disabled`,
   and the Unread tab showed the empty state "Nothing to catch up on."
5. **Live increment without reload, via a second "session."** Task 20 (the phone simulator) is not
   built yet — `web/src/features/sim/SimulatorPage.tsx` is a one-line placeholder stub (I read it to
   confirm before assuming otherwise), so I used the brief's alternative ("or a second session") by
   directly updating one conversation's `sla_due_at`/`sla_breach_notified_at` in the running SQLite
   DB (via a separate Python process) to make it newly overdue, while the browser tab stayed open on
   `/app/notifications` with no navigation. I polled the unread-count API in a background Monitor
   task (not the browser) until it rose. Once the next `sla.sweep` tick (server's 30s recurring job)
   fired, I re-snapshotted the *same, un-navigated* browser tab: the nav badge had updated live to
   "Alerts 1" and a new row ("Response overdue: Ines Haddad · 508 … now") appeared at the top of the
   list — proving Task 11's `notification.created` → `qk.notificationsAll`/`qk.unreadCount`
   invalidation drives this task's hooks with no poll and no reload.

Nothing in Step 6 was unrunnable — Playwright MCP tools were available and I used them for every
check above.

## `npx tsc -b`

Clean, no output, no warnings.

## Files changed

- `web/src/api/hooks/notifications.ts` (new)
- `web/src/features/notifications/NotificationsPage.tsx` (new)
- `web/src/features/notifications/NotificationsPage.test.tsx` (new)
- `web/src/AppLayout.tsx` (modified — `Shell` wrapper feeding `unreadCount`)
- `web/src/routes.tsx` (modified — real `NotificationsPage` route)
- `web/src/routes.test.tsx` (modified — fetch mock no longer blanket-401s the new
  `unread-count` endpoint the Shell now calls on every `/app/*` route; see defect note above)

## Self-review findings

- **Completeness**: 10/10 notification tests pass (brief said 11; see prose/code mismatch note
  above — not a code defect). Badge renders only when `unreadCount` is truthy (verified both in
  the vitest suite via `AppShell.test.tsx`'s existing coverage and live in the browser: badge
  vanished entirely at count 0, not "Alerts 0").
- **Quality**: opening a notification marks it read and navigates in one click (verified live and
  in test `marks a notification read when it is opened`). Unlinkable notifications render as plain
  text with no link (verified in test and by code review of `linkFor`). `AppShell.tsx` itself was
  not touched — it remains fetch-free; only `AppLayout.tsx`'s new `Shell` fetches, per the brief.
- **Discipline**: no `NotificationBell.tsx` created. No scope beyond the brief's file list, except
  the one-line-targeted fix to `routes.test.tsx`'s mock, which was necessary to keep the full suite
  green and is documented above as a real defect this task's (prescribed) wiring exposed.
- **Testing**: full suite is 323/323 passing, no `act()` warnings or unhandled rejections in the
  output. TDD sequence (RED then GREEN) is captured above with real command output, not inferred.

## Issues or concerns

- The brief's "11 notification tests" claim doesn't match the 10 `it()` blocks actually in Step 2's
  code — harmless, flagged rather than silently reconciled.
- `routes.test.tsx`'s blanket-401 fetch mock needed a one-line-targeted change (see above) because
  this task's prescribed `AppLayout` wiring makes every `/app/*` route fetch for the first time.
  This is a genuine, reproducible side effect of the plan's own design (verified before/after via
  git stash), not a mistake in my implementation — flagging it as the kind of defect the dispatch
  asked me to surface rather than silently patch around.
- I did not attempt to stop the several pre-existing `dev_start.py`/`vite` background processes
  already running in this environment (from other sessions) — only confirmed my own server/web
  instances worked for verification. I left all of them running rather than risk killing another
  session's server.
