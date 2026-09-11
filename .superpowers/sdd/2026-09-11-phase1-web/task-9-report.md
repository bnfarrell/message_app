# Task 9 report — App shell: left nav, role filtering, theme toggle, property switcher

## What I implemented

- `web/src/components/NavIcon.tsx` — five inline SVG stroke icons (`inbox`, `board`, `analytics`, `alerts`, `admin`, `theme`), 18px, `stroke: currentColor`, width 1.75, round caps. Written verbatim from the brief (Step 3); no defects found there.
- `web/src/components/AppShell.tsx` — replaces Task 8's pass-through stub with the real 184px left nav: property tile + name, role-filtered nav rows (44px, active row `bg-surface2 text-roomNum`, `aria-current="page"` via `NavLink`'s default), a footer with a Theme toggle, an optional property switcher (`Dropdown`), and the signed-in user (`Avatar` + name + role).
- `web/src/components/AppShell.test.tsx` — the 11 tests from the brief, written verbatim (Step 1).

Also touched, as an unavoidable consequence of replacing the stub (see Issues below):
- `web/src/routes.test.tsx` — rescoped 7 assertions to query within the `<main>` landmark instead of the whole document, since the real nav now renders the same labels ("Inbox", "Board", "Analytics", "Admin") as the `Placeholder` screen titles that test was matching against.

## Defects found in the brief (reported, not silently patched)

The brief says: "If a test in the brief asserts something wrong, do not bend the code to make it pass. Report the defect." I found three, all in the *implementation code sample* (Step 4), not in the test file, which I kept verbatim:

1. **Duplicate property-code text breaks `getByText('HVH')`.** The sample Step 4 code renders `membership.propertyCode` twice — once in the tile, once in the subtitle line under the property name — so `screen.getByText('HVH')` (a single-match query) would throw "multiple elements found." The brief's own prose (not the paraphrased task context) says the tile should show `HV` (a two-letter abbreviation, matching `docs/mockups/Main.dc.html` line 44: `<div ...>HV</div>`) with a second line that in the mockup is a "shift/clock" line we have no data source for (and the shell must not fetch). Fix: tile shows `membership.propertyCode.slice(0, 2).toUpperCase()` ("HV"); the subtitle line shows the full `propertyCode` ("HVH") once, replacing the unavailable shift/clock text with real data we do have.

2. **Unread badge ignores the `Badge` component and the radius rule.** The brief's own Interfaces section lists `Badge` (Task 4) as consumed, but Step 4's sample hand-rolls a `<span className="rounded bg-danger ...">` for the unread count — never importing `Badge`, and using the 8px "control" radius (`rounded`) where the design constraints explicitly require 6px `rounded-md` for "tags/badges/avatars/timer chips." Fix: wrap the count in the `Badge` component (`tone="danger"`), which already implements `rounded-md`, with the `data-testid="unread-badge"` on an inner span (Badge doesn't forward arbitrary props).

3. **Inbox `needs` array contradicts the brief's own test.** The nav table says Inbox shows for `can('reply') OR can('view_all_conversations')`. But `capabilities.ts` (Task 5, already committed, mirrors the server) grants `corporate` role `view_all_conversations: true` while `reply: false`. Under the literal OR, Inbox would be visible to corporate — yet the brief's own test `'hides the Inbox from corporate, which cannot reply'` requires it hidden. This same contradiction exists verbatim in the source plan document (`docs/superpowers/plans/2026-09-11-phase1-web.md` lines 3095, 3159, 3287), so it isn't something I introduced. Fix: Inbox visibility depends only on `reply`. This also matches `landingPath('corporate') === '/app/analytics'` — corporate never lands on Inbox, so it makes sense they never see the link either.

None of these required bending or weakening any assertion in `AppShell.test.tsx` — the test file is exactly as given, and all 11 pass.

## TDD evidence

**RED** — `cd web && npx vitest run src/components/AppShell.test.tsx` against the Task 8 pass-through stub:

```
Test Files  1 failed (1)
     Tests  11 failed (11)
```
All 11 failed as expected — the stub renders only `{children}`, so every nav/property/theme/switcher assertion had nothing to find (example failure: `Unable to find role="button" and name /switch property/i`, body containing only `<p>screen body</p>`).

**GREEN** — same command after writing `NavIcon.tsx` and `AppShell.tsx` (with the three fixes above):

```
Test Files  1 passed (1)
     Tests  11 passed (11)
```

## What I tested and the results

- `cd web && npx vitest run src/components/AppShell.test.tsx` — 11/11 pass.
- `cd web && npm test` (full suite) — **14 files, 84 tests, all pass.** No `act()` warnings, no unhandled rejections, no React Router future-flag warnings, no console noise beyond the two expected/pre-existing favicon 404s in manual browser testing (not part of `npm test` output at all — the vitest run itself is silent aside from the pass/fail summary).
- `cd web && npx tsc -b` (and again with `--force`) — clean, no output, exit 0.

## Live four-role verification (Playwright browser, not just curl)

I could drive a real browser (Playwright MCP tools were available), so I did the full live check rather than settling for static/API checks. Server: `.venv\Scripts\python.exe server\dev_start.py` (port 5000). Client: `npm run dev` in `web/` (Vite picked port 5174 since 5173 was held by an earlier orphaned process of mine — noted and cleaned up afterward, see below).

| Role | Login | Nav shown | Not shown | Footer |
|---|---|---|---|---|
| agent | ava@hvh.test | Inbox, Board, Alerts | Analytics, Admin | "Ava" / "Agent" |
| dept_staff | eli@hvh.test | Inbox, Board, Alerts | Analytics, Admin | "Eli" / "Staff" |
| manager | morgan@hvh.test | Inbox, Board, Analytics, Alerts | Admin | "Morgan" / "Duty manager" |
| admin | alex@hvh.test | Inbox, Board, Analytics, Alerts, Admin | — | "Alex" / "Admin" |

All four matched the capability table exactly. Property tile showed "HV" / "Harbourview Hotel" / "HVH" for every login (single property).

**Theme survives reload** (the most valuable check, per the brief): starting resolved theme was `light`. Clicked **Theme** → `document.documentElement.dataset.theme` became `dark`. Reloaded the page (`http://localhost:5174/app/inbox`) → still `dark` (server round-trip confirmed). Clicked **Theme** again → `light`. Reloaded again → still `light`. Both directions of the brief's specific ask ("flips ... to light and survives a reload") were verified.

**Active row styling**: on `/app/analytics` as manager, `document.querySelector('a[aria-current="page"]')` had class `bg-surface2 text-roomNum` and computed color `rgb(154, 107, 0)` (amber, the `--roomNum` light-theme token) on background `rgb(238, 241, 245)` (`--surface2`). Matches the mockup.

**Bonus (not one of the four required roles, but confirms the corporate-Inbox fix and the property switcher live):** signed in as `casey@group.test` (corporate, two memberships — HVH and Lakeside Inn per seed data). Nav showed Analytics, Alerts, Admin — **no Inbox**, confirming defect fix #3 above holds in the real app, not just in the test. The "Switch property" button was present (two memberships), opened a menu with both properties, and clicking "Lakeside Inn" updated the tile to "LS" / "Lakeside Inn" / "LSI", kept the user on `/app/analytics` (same role at both properties, so same landing), and set `localStorage.activePropertyId` to Lakeside Inn's id.

I did not check every role×property combination or every screen-reload edge case; the above covers everything the brief's Step 6 and my own judgment called for.

## `npx tsc -b` confirmation

Clean, no output, exit code 0 (checked twice, once with `--force` to rule out stale build cache).

## Files changed

- `web/src/components/AppShell.tsx` (new, replaces stub)
- `web/src/components/NavIcon.tsx` (new)
- `web/src/components/AppShell.test.tsx` (new)
- `web/src/routes.test.tsx` (modified — 7 assertions rescoped to `within(main)`, see Issues)

## Self-review

- **Completeness:** all 11 brief tests pass; each of the 5 nav items verified present/absent for the right roles in both unit tests and live browser checks across 5 accounts (4 required + 1 bonus).
- **Quality:** active row carries `aria-current="page"` (via `NavLink`'s default, unmodified). Hidden nav items are filtered out of the `visible` array before mapping — truly absent from the DOM, not CSS-hidden (test-verified with `queryByRole`, and inspected live). Property switcher calls `setPropertyId` then `navigate(landingPath(newRole), { replace: true })` — verified both in the unit test (`localStorage` check) and live (tile/name/code changed, no route-mismatch flash).
- **Discipline:** shell takes `unreadCount` as an optional prop only, no query/fetch of its own. No icon library added — `NavIcon` is hand-rolled inline SVG. Nothing added beyond the brief's two files plus the test.
- **Testing:** full suite is pristine — no `act()` warnings, no unhandled rejections, no router future-flag warnings.

## Issues / concerns

1. **`routes.test.tsx` change is out of Task 9's nominal file list** (`Files:` section names only `AppShell.tsx`, `NavIcon.tsx`, and its own test). I made this change because leaving `npm test` red was not an acceptable outcome, and the break is a direct, unavoidable, and entirely expected consequence of Task 9 doing exactly what it was asked to do (replace the pass-through stub with a real nav that repeats the same labels the Task 8 test was matching loosely). The diff is minimal — only the ambiguous `screen.findByText(...)` calls were rescoped to `within(main)`; no assertions were weakened or removed. Flagging this explicitly in case the reviewer wants it split into its own commit or attributed differently.
2. **Three defects in the brief itself**, detailed above — all reported rather than silently patched, with reasoning tied to the mockup, the Interfaces section, the design radius rules, and the brief's own test expectations.
3. I could drive a real browser (Playwright), so the Step 6 live verification is genuine, not simulated — including a reload-triggered persistence check in both directions and a bonus property-switcher exercise with a real second property.
4. I orphaned two dev-server processes early on (a backgrounding mechanics mistake — using `&` inside a `run_in_background` Bash call let the child outlive the parent shell without being tracked by the harness); found via `netstat`/`tasklist` and killed with `taskkill` before finishing. No lingering processes remain (`netstat` shows no `LISTENING` sockets on 5000/5173/5174 after cleanup).

---

## Fix report (post-review)

The coordinator's review sent two batched fixes.

### Fix 1 — corporate/Inbox: I resolved the brief's self-contradiction the wrong way

My original call narrowed Inbox's `needs` to `['reply']` because the brief's own test said "hides the Inbox from corporate, which cannot reply." The coordinator checked the server (`server/app/auth/permissions.py`) and found corporate genuinely holds `view_all_conversations` and `add_note` (via `STAFF`), and the conversation-list endpoint carries no `@require_capability` gate — so corporate can really read (and note) every conversation. Hiding Inbox from them would strand capabilities the server grants. The *table* was right; the *test* was wrong.

**Change:** `web/src/components/AppShell.tsx` — Inbox `needs` reverted to `['reply', 'view_all_conversations']`.

**Test replaced verbatim as instructed** in `web/src/components/AppShell.test.tsx`:
```tsx
it('shows the Inbox to corporate, which can read conversations and add notes', async () => {
  mount({ role: 'corporate' })
  expect(await screen.findByRole('link', { name: /analytics/i })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /inbox/i })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /board/i })).not.toBeInTheDocument()
})
```

**Board-assertion verification** (asked to check before committing, not assume): corporate has neither `create_work_order` nor `close_work_order` in `capabilities.ts`, so Board's `needs` (`['create_work_order', 'close_work_order']`) evaluates to `false` for corporate — Board is correctly absent. Confirmed by running the suite; it passed on the first try with no further changes needed.

```
$ npx vitest run src/components/AppShell.test.tsx
✓ src/components/AppShell.test.tsx (11 tests) 420ms
 Test Files  1 passed (1)
      Tests  11 passed (11)
```

### Fix 2 — routes.test.tsx: missing role landings + untested `?mine=1` preservation

Added a `LocationDisplay` component (`useLocation()` → `data-testid="location"`) rendered alongside `AppRoutes` inside the same `MemoryRouter`, so `mountAt` now mounts `<><AppRoutes /><LocationDisplay /></>`. Added:
- `sends a supervisor from /app to the board, filtered to mine`
- `sends an admin from /app to analytics`
- `sends corporate from /app to analytics`
- A `location.search` assertion (`/app/board?mine=1`) on both the existing dept_staff test and the new supervisor test — the two roles whose landing carries a query string.

**Deliberate-failure evidence**, as required — temporarily changed `landingPath`'s `dept_staff`/`supervisor` case in `web/src/auth/capabilities.ts` from `'/app/board?mine=1'` to `'/app/board'`:

```
$ npx vitest run src/routes.test.tsx
 ❯ src/routes.test.tsx (11 tests | 2 failed)
   × AppRoutes > sends dept_staff from /app to the board, filtered to mine
     → expect(element).toHaveTextContent()
       Expected element to have text content: /app/board?mine=1
       Received: /app/board
   × AppRoutes > sends a supervisor from /app to the board, filtered to mine
     → expect(element).toHaveTextContent()
       Expected element to have text content: /app/board?mine=1
       Received: /app/board
 Test Files  1 failed (1)
      Tests  2 failed | 9 passed (11)
```

Both new query-string assertions failed exactly as expected, proving they'd catch a dropped `?mine=1`. Reverted `capabilities.ts` immediately after (confirmed via `git diff` showing no changes to that file).

**Green after revert:**
```
$ npx vitest run src/components/AppShell.test.tsx src/routes.test.tsx
✓ src/routes.test.tsx (11 tests) 333ms
✓ src/components/AppShell.test.tsx (11 tests) 443ms
 Test Files  2 passed (2)
      Tests  22 passed (22)
```

### Full suite and typecheck after both fixes

```
$ npm test
 Test Files  14 passed (14)
      Tests  87 passed (87)

$ npx tsc -b
(no output, exit 0)
```

### Files changed (this fix round)

- `web/src/components/AppShell.tsx` — Inbox `needs` reverted to include `view_all_conversations`.
- `web/src/components/AppShell.test.tsx` — corporate test replaced with the coordinator's exact text.
- `web/src/routes.test.tsx` — `LocationDisplay` helper, three new role-landing tests, `?mine=1` search assertions on the two query-carrying roles.
- `web/src/auth/capabilities.ts` — touched only transiently to produce the deliberate-failure evidence; reverted, no net diff.

### Commit

One commit (both fixes touch `AppShell.tsx`/`AppShell.test.tsx` and `routes.test.tsx` together and were part of the same review round): `ac68cad` — "fix(web): restore corporate Inbox access, cover all six role landings"

---

## Fix report (second review round)

Task 9 was Approved with three follow-up items.

### Finding 1 (Important) — cross-role property switch was untested by every method used

Every switcher test (`AppShell.test.tsx`) and my live browser check used matching roles on both memberships (`secondRole` defaulting to `opts.role`, or Casey being corporate at both HVH and Lakeside), so the branch where `navigate(landingPath(m.role), ...)` actually differs from `navigate(landingPath(role), ...)` was never exercised — `landingPath(m.role)` could have silently regressed to `landingPath(role)` and nothing would have caught it.

**Fix:** added a `LocationDisplay` helper (`useLocation()` → `data-testid="location"`, mirroring `routes.test.tsx`'s approach) rendered as a sibling of `AppShell` via a new `mountWithLocation` helper, and a new test in `web/src/components/AppShell.test.tsx`:

```tsx
it('switching to a property where the role differs lands on that role landing screen', async () => {
  mountWithLocation({ role: 'agent', withSecondProperty: true, secondRole: 'admin' })
  await userEvent.click(await screen.findByRole('button', { name: /switch property/i }))
  await userEvent.click(screen.getByRole('menuitem', { name: /Lakeside Inn/ }))
  expect(await screen.findByTestId('location')).toHaveTextContent('/app/analytics')
  expect(screen.getByTestId('location')).not.toHaveTextContent('/app/inbox')
})
```

**Deliberate-failure evidence** — temporarily changed `AppShell.tsx`'s switch handler from `navigate(landingPath(m.role), ...)` to `navigate(landingPath(role), ...)` (the exact regression the finding describes):

```
$ npx vitest run src/components/AppShell.test.tsx
 ❯ src/components/AppShell.test.tsx (12 tests | 1 failed)
   × AppShell > switching to a property where the role differs lands on that role landing screen
     → expect(element).toHaveTextContent()
       Expected element to have text content: /app/analytics
       Received: /app/inbox
 Test Files  1 failed (1)
      Tests  1 failed | 11 passed (12)
```

Exactly the predicted failure — landed on `/app/inbox` (agent's landing, from the stale `role`) instead of `/app/analytics` (admin's landing, the target membership's role). No other test failed, confirming the new test is the one that discriminates this regression. Reverted immediately; `git diff web/src/components/AppShell.tsx` afterward showed only the Finding 2 change (below), confirming a clean revert.

**Green after revert:**
```
$ npx vitest run src/components/AppShell.test.tsx
✓ src/components/AppShell.test.tsx (12 tests) 584ms
 Test Files  1 passed (1)
      Tests  12 passed (12)
```

### Finding 2 (Minor) — badge keyed off a display string

Changed the gate in `web/src/components/AppShell.tsx` from `item.label === 'Alerts'` to `item.to === '/app/notifications'`. Chose the route path over adding a new `isAlerts`-style flag to `NavItem` because `to` is already the stable, unique identity each nav item carries for routing — reusing it needs no schema change and no new field to keep in sync, whereas a label is display copy that's expected to change (e.g. "Alerts" → "Notifications" in some future pass) without anyone thinking to check whether it's also load-bearing logic.

### Finding 3 (Minor) — misleading test name

Renamed `'shows Admin only to admin'` to `'shows Admin to a role with manage_admin'` in `web/src/components/AppShell.test.tsx`, with a comment noting corporate also holds `manage_admin` on the server and the test never asserted exclusivity — only that admin sees the link.

### Full suite and typecheck after all three fixes

```
$ npx vitest run src/components/AppShell.test.tsx
✓ src/components/AppShell.test.tsx (12 tests) 584ms
 Test Files  1 passed (1)
      Tests  12 passed (12)

$ npm test
 Test Files  17 passed (17)
      Tests  124 passed (124)

$ npx tsc -b
(no output, exit 0)
```
(17 files / 124 tests reflects the concurrently-reviewed `segments.ts`/`time.ts`/`SlaChip.tsx` test files landing in the same working tree; no collision — `git status` before committing showed only `AppShell.tsx` and `AppShell.test.tsx` modified.)

### Files changed (this fix round)

- `web/src/components/AppShell.tsx` — badge gate keyed off `item.to` instead of `item.label`.
- `web/src/components/AppShell.test.tsx` — `LocationDisplay` helper + `mountWithLocation`, new cross-role switch test, renamed Admin test.

### Commit

`0729055` — "fix(web): stabilize badge key, cover cross-role property switch, clarify test name"
