# Task 16: Work-order board, detail and transitions — Report

## What I implemented

Followed the brief's file list and TDD order exactly:

- `web/src/features/board/transitions.ts` — `TRANSITIONS`, `OPEN_STATUSES`, `BOARD_COLUMNS`, `STATUS_LABELS`, `CLOSING_STATUSES`, `allowedTransitions`, `canTransition`, `PRIORITY_TONE`. Pure data/functions, no React import.
- `web/src/features/board/TransitionButtons.tsx` — renders only reachable transitions, filters the three closing statuses (`complete`, `verified`, `cancelled`) by `can('close_work_order')`, asks for a reason via `Dialog`+`Textarea` for `blocked`/`cancelled`, surfaces `patch.error` as `role="alert"`.
- `web/src/features/board/WorkOrderCard.tsx` — room/location mono, priority badge, assignee avatar, title, department · age footer, links to `/app/work-orders/<id>`.
- `web/src/features/board/BoardPage.tsx` — header with active/urgent counts, filter tabs (All/Mine/per-department/Urgent), Board/List toggle, five open-status columns, honours `?mine=1` on entry and keeps filters in the URL.
- `web/src/features/board/WorkOrderDetailPage.tsx` — back link, `#<id>`, title, room, status/priority badges, two-column field block, description with source-conversation link, resolution/timeline newest-first with comments, `TransitionButtons` in the header.
- `web/src/components/ui/Avatar.tsx` — added `className?: string`, threaded through `cn(...)` (Step 5 requirement).
- `web/src/routes.tsx` — replaced the `board` and `work-orders/:id` placeholders with the real screens.
- Tests: `transitions.test.ts` (9), `TransitionButtons.test.tsx` (11), `BoardPage.test.tsx` (8 — see count note below), `WorkOrderDetailPage.test.tsx` (7).
- `web/src/routes.test.tsx` — updated the two Board-landing tests (see "Pre-existing test needed updating" below).

I used the brief's code essentially verbatim, with two small deviations from the literal snippets, both mechanical:
- `Field({ value: React.ReactNode })` in `WorkOrderDetailPage.tsx` → I imported `type { ReactNode } from 'react'` and typed it as `ReactNode` instead of the bare `React.ReactNode`, matching how every other file in this codebase types children (`React` is never used as an ambient global here; a bare `React.ReactNode` reference does not compile under this project's TS config).

## What I tested and the results

`cd web && npm test -- --run` → **287 passed (35 files)**, no `act()` warnings, no unhandled rejections, no other console noise beyond the pre-existing suite's own expected assertions.

`cd web && npx tsc -b` → clean, no output, no errors, no warnings.

## TDD evidence

**RED** — `cd web && npx vitest run src/features/board` after writing `transitions.ts`, `transitions.test.ts`, and `TransitionButtons.test.tsx` (before `TransitionButtons.tsx` existed):

```
✓ src/features/board/transitions.test.ts (9 tests)
❯ src/features/board/TransitionButtons.test.tsx (0 test)
FAIL src/features/board/TransitionButtons.test.tsx
Error: Failed to resolve import "./TransitionButtons" from
"src/features/board/TransitionButtons.test.tsx". Does the file exist?
Test Files  1 failed | 1 passed (2)
     Tests  9 passed (9)
```
Expected: the brief's Step 1 has `transitions.ts` fully implemented before its own test file is written in Step 2, so `transitions.test.ts` was never going to be RED in isolation — it's a straight assertion of the matrix against my Step-1 code. The genuine RED signal at this checkpoint is `TransitionButtons.test.tsx` failing because `TransitionButtons.tsx` doesn't exist yet, which is exactly what happened.

**GREEN** — `cd web && npx vitest run src/features/board` after Steps 4–8 (all screens + tests written):

```
✓ src/features/board/transitions.test.ts (9 tests)
✓ src/features/board/WorkOrderDetailPage.test.tsx (7 tests)
✓ src/features/board/BoardPage.test.tsx (8 tests)
✓ src/features/board/TransitionButtons.test.tsx (11 tests)
Test Files  4 passed (4)
     Tests  35 passed (35)
```

Two of those tests required fixing genuine defects in the brief's literal test code before they'd pass against correct component code — documented below, not worked around in production code.

## Transition matrix vs. the server

Diffed `web/src/features/board/transitions.ts`'s `TRANSITIONS` against `server/app/domain/work_orders.py:38-47` (`TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]]`) key by key, both directions:

| from | server (`.py`) | client (`.ts`) | match |
|---|---|---|---|
| open | {assigned, in_progress, cancelled} | [assigned, in_progress, cancelled] | yes |
| assigned | {in_progress, open, cancelled} | [in_progress, open, cancelled] | yes |
| in_progress | {blocked, complete, cancelled} | [blocked, complete, cancelled] | yes |
| blocked | {in_progress, cancelled} | [in_progress, cancelled] | yes |
| complete | {verified, in_progress} | [verified, in_progress] | yes |
| verified | {} | [] | yes |
| cancelled | {} | [] | yes |

Exact match. Also diffed `OPEN_STATUSES` — server's `[S.open, S.assigned, S.in_progress, S.blocked, S.complete]` vs. client's `['open', 'assigned', 'in_progress', 'blocked', 'complete']` — identical order and membership, `verified`/`cancelled` excluded from both. Diffed the closing-transition capability gate against `server/app/auth/permissions.py`'s `CAPABILITIES["close_work_order"] = {dept_staff, supervisor, manager, admin}` — matches `web/src/auth/capabilities.ts`'s existing `close_work_order` list exactly (already in place from an earlier task; I didn't touch it), and `CLOSING_STATUSES = ['complete', 'verified', 'cancelled']` matches the three statuses the server would otherwise let an unauthorized role attempt.

## Defects found in the brief (reported, not silently patched)

1. **`BoardPage.test.tsx`'s `ORDERS` fixture undercounts urgent by one.** `w-2` ("Toilet running") is built with `aWorkOrder({ id: 'w-2', status: 'assigned', ... })` and no `priority` override. `aWorkOrder`'s factory default priority is `'urgent'` (`web/src/test/factories.ts:144`), so as literally written the fixture has three urgent orders (`w-2`, `w-3`, `w-4`), not two — while the test asserts `/4 active · 2 urgent/`. This is a test-fixture defect, not a production bug: I added `priority: 'normal'` to `w-2`'s factory call (the fixture's evident intent, matching its non-urgent title) so the count assertion holds against correct code. Verified the original (unpatched) test fails against my BoardPage with the actual urgent count of 3 before making this fix.
2. **`BoardPage.test.tsx`'s `?mine=1` test has a race.** It `waitFor`s only on the mocked `fetch` having been called with `mine=true`, then immediately does a synchronous `screen.getByRole('tab', ...)`. `fetch` being called happens before the response promise resolves and React re-renders with the loaded data, so the synchronous assertion can run while the board is still showing its `Spinner`. Changed the final assertion to `await screen.findByRole(...)` (same as every other async assertion in this file and the sibling test files), which waits for the actual DOM update instead of racing it. Confirmed this was a genuine timing defect, not a component bug, by rerunning the original assertion in isolation and observing the spinner-only DOM at failure time (no fetch/query bug — data really wasn't rendered yet).
3. **Prose/count mismatch (harmless).** The brief's Step 10 says "9 board tests"; the literal `BoardPage.test.tsx` code block in Step 8 contains 8 `it(...)` blocks. I implemented the file as given — 8 tests — and did not invent a ninth. Also, Step 11's live-verification prose says "the 15 seeded work orders spread across the five columns"; the actual seed under `?view=all` (excluding closed) is 17 active work orders across the five open columns (2/8/2/1/4). Both are just prose/count mismatches against the literal fixtures — reported, not corrected in test/production code since they don't affect pass/fail.

No other defects found; the rest of the literal code in the brief compiled and passed as given, against my reading of Task 15's hooks and Task 12's factories/types.

## Pre-existing test needed updating

`web/src/routes.test.tsx`'s two Board-landing tests (`sends dept_staff...`, `sends a supervisor...`) predate this task and asserted `findByText('Board')` inside `<main>`, which worked against the old `Placeholder` screen. Now that `BoardPage` is real, it makes its own API calls; this file's blanket `beforeEach` mocks every fetch with a 401, so the real `BoardPage` renders its `EmptyState` ("Could not load the board" / "Not signed in") instead of literal "Board" text — same situation the file's own comment already documents for the Inbox test after Task 12 replaced that placeholder ("Task 12 replaced the Inbox placeholder... the location is the stable signal that we landed"). I applied the identical fix: dropped the `findByText('Board')` assertion and kept only the location-testid assertion (now wrapped in `waitFor` since it's async), adding a comment in the same style as the existing Inbox-test comment. This is a routing test, squarely in scope for a task that replaces routed placeholders, and mirrors the precedent already in the file rather than inventing a new pattern.

## Live verification (Step 11)

I have a live browser (Playwright MCP) in this environment, so I ran the full scenario for real rather than skipping it.

Server: `.venv\Scripts\python.exe server\dev_start.py` (started clean, logged "Database already has data, skipping seed", listening on `http://127.0.0.1:5000`).
Web: `npm run dev` in `web/` (Vite picked port 5177 since 5173–5176 were already in use by other sessions in this environment; proxy config confirmed `/api` → `127.0.0.1:5000`).

1. **Logged in as `eli@hvh.test`.** Landed on `http://localhost:5177/app/board?mine=1`. The **Mine** tab showed `[selected]` in the accessibility tree (equivalent to `aria-selected="true"`). Observed.
2. **Switched to All.** Header read "17 active · 3 urgent" (not the brief's guessed "15" — see defect #3 above); the five columns showed Open 2, Assigned 8, In progress 2, Blocked 1, Complete 4 = 17, spread across all five as required. Observed.
3. **Opened an `open` work order** ("219 · Elevator B intermittent door fault"). Exactly three buttons rendered: **Assigned**, **In progress**, **Cancelled** — no Complete, no Blocked, no Verified. Observed, matches the matrix.
4. **Clicked In progress.** Status badge updated to "In progress"; buttons became **Blocked**, **Complete**, **Cancelled** (Complete rendered as the primary/amber button, Cancelled as danger). Observed.
5. **Clicked Blocked, typed "Waiting on replacement door sensor from vendor", clicked Confirm.** Status badge updated to "Blocked"; buttons narrowed to **In progress** and **Cancelled** only (matching `blocked → [in_progress, cancelled]`); the timeline's newest entry read "status changed → blocked / Eli Engineer · 03:58 / Waiting on replacement door sensor from vendor" — the reason is visible. Observed.
6. **Logged out, logged in as `ava@hvh.test` (agent), navigated to the same work order.** Status showed "Blocked"; only **In progress** was offered (Cancelled correctly hidden, since agent lacks `close_work_order`). Clicked it to move the order into `in_progress` and confirmed the harder case the brief actually asks for: from `in_progress`, agent Ava sees only **Blocked** — **Complete** and **Cancelled** are both absent. Observed.

No step was skipped; all six were driven and observed directly in a real browser against the real server, not simulated. (Note: there was no logout control in the UI's nav — I used `POST /api/auth/logout` directly via `page.evaluate`, which is what `useLogout` calls, then navigated to `/login` to switch users. This is a UI gap outside this task's scope, not a defect I introduced or was asked to fix.)

The one console error seen throughout (`401 @ /api/auth/me`, `WebSocket ... closed before the connection is established`) occurred only around login/logout transitions and is pre-existing session/websocket-reconnect behavior, unrelated to the board/detail code.

## `npx tsc -b`

Clean — no output, no errors, no warnings.

## Files changed

- `web/src/features/board/transitions.ts` (new)
- `web/src/features/board/transitions.test.ts` (new)
- `web/src/features/board/TransitionButtons.tsx` (new)
- `web/src/features/board/TransitionButtons.test.tsx` (new)
- `web/src/features/board/WorkOrderCard.tsx` (new)
- `web/src/features/board/BoardPage.tsx` (new)
- `web/src/features/board/BoardPage.test.tsx` (new)
- `web/src/features/board/WorkOrderDetailPage.tsx` (new)
- `web/src/features/board/WorkOrderDetailPage.test.tsx` (new)
- `web/src/components/ui/Avatar.tsx` (modified — added `className`)
- `web/src/routes.tsx` (modified — wired Board/WorkOrderDetail routes)
- `web/src/routes.test.tsx` (modified — updated two pre-existing Board-landing tests for the real screen, per the precedent already in the file for the Inbox screen)

## Self-review findings

- **Completeness:** 9 matrix tests, 11 button tests, 8 board tests (brief's own literal code has 8, not the 9 claimed in its prose — reported above), 7 detail tests. All pass. Full suite: 287/287.
- **Quality:** matrix diffed key-by-key against the server and matches exactly in both directions (table above). Closing transitions (`complete`, `verified`, `cancelled`) are gated on `can('close_work_order')` in `TransitionButtons.tsx`, matching `permissions.py`'s `close_work_order` role set. `?mine=1` is read from `useSearchParams()` on mount and every filter change goes through `setParam`/`setParams` with `{ replace: true }`, keeping the URL in sync. A 409 from the server is not swallowed — `patch.error` renders as `role="alert"` text sourced from `ApiError.message`, tested and confirmed live at the button level (the `TransitionButtons.test.tsx` 409 test) and reviewed for behavior in the actual PATCH flow.
- **Discipline:** no photo affordance anywhere in `WorkOrderDetailPage.tsx`. Nothing beyond the brief's file list was added. Task 15's `useWorkOrders`/`useWorkOrder`/`usePatchWorkOrder` hooks were consumed as-is, not modified.
- **Testing:** re-ran the full suite twice at the end (`npm test -- --run`) — 287/287, no `act()` warnings, no unhandled promise rejections, no stray console output. `npx tsc -b` clean on a second run as well.

## Issues or concerns

- None blocking. The two test-code fixes (urgent-count fixture, `?mine=1` race) and the `routes.test.tsx` update are documented above as defects found and corrected, per the standing instruction to report rather than silently bend production code — production code was not changed to accommodate either fix.
- The dev environment has several leftover `dev_start.py`/`vite` processes from earlier sessions that predate this task; I did not attempt to clean those up since I can't safely distinguish which are mine versus other concurrent work, beyond stopping the two background tasks I launched (whose wrapper processes had already exited by the time I checked, which is expected — Vite/Flask keep running in the parent script's `&`-backgrounded child once the wrapper returns).
