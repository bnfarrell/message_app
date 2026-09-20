# Task 13 Report: LogPage, route and nav

## What was implemented

- `web/src/features/log/LogPage.tsx` (new): the log screen — header, `<LogComposer>`,
  filters (shift select, department select, "Mentioning me" checkbox), a `role="tablist"`
  with a single selected `role="tab"` ("Posts"), the pinned block (rendered only when
  `feed.pinned` is non-empty), and entries grouped under day headings
  (`Today · N posts`, or a full weekday/month/day string for earlier days). Loading state
  is a `Spinner`, error state and the empty-feed state both use `EmptyState`, matching
  `MessagesPage`'s pattern.
- `web/src/lib/time.ts`: added `dayKey(iso)`, a small helper returning the viewer's local
  calendar day as `YYYY-MM-DD`, reading `Date`'s local getters (`getFullYear`/`getMonth`/
  `getDate`), not the UTC ones. No date library added.
- `web/src/components/NavIcon.tsx`: added `'log'` to the `IconName` union and its SVG path
  to `PATHS`, exactly as specified in the brief (ruled-notebook glyph).
- `web/src/components/navModel.ts`: added `{ label: 'Log', to: '/app/log', icon: 'log',
  needs: [] }` to the Overview group, after Messages.
- `web/src/routes.tsx`: imported `LogPage` and added `<Route path="log" element={<LogPage
  />} />` inside `AppLayout`, after `messages/:id`. No `RequireCapability` wrapper
  (`view_log` is granted to every role).
- Two pre-existing tests updated because they hardcoded the *exact* nav-item list for a
  capability-less role, and adding a `needs: []` item legitimately changes that list:
  - `web/src/components/AppShell.test.tsx` — `'keeps only the capability-free items...'`
    now expects `['Alerts', 'Messages', 'Log']`.
  - `web/src/components/CommandPalette.test.tsx` — `'offers an agent only what an agent
    can reach...'` now expects `'Log'` in the option list.

## Tests written

- `web/src/features/log/LogPage.test.tsx` (new, 7 tests) — uses the same integration
  pattern already established by `LogComposer.test.tsx`/`LogEntryCard.test.tsx`
  (`renderWithProviders` + `SessionProvider` + a `fetch` mock keyed by URL substring),
  rather than mocking `useLogFeed` directly, so filter assertions check the *actual*
  outgoing request URL:
  1. Tab strip: exactly one tab, labelled "Posts", `aria-selected="true"`.
  2. Day grouping: two entries created "now" render one heading `Today · 2 posts`.
  3. Pinned block renders, labelled "Pinned", above the day groups, when
     `feed.pinned` is non-empty.
  4. Pinned block is entirely absent when `feed.pinned` is empty.
  5. Selecting "Overnight" in the shift `<select>` causes a subsequent fetch whose URL
     contains `shift=overnight`.
  6. Checking "Mentioning me" causes a subsequent fetch whose URL contains
     `mentioningMe=true`.
  7. An empty feed (`entries: []`, `pinned: []`) renders an empty-state message
     ("No log entries yet"), not a bare page.
- `web/src/lib/time.test.ts` — added a `describe('dayKey', ...)` block (3 tests):
  local-day format, same local day at different times keys equal, and either side of
  local midnight keys differently.
- `web/src/components/navModel.test.ts` — added the exact test the brief specified
  (`visibleNavGroups(() => false)` still surfaces `/app/log`).

## TDD evidence

RED (before any implementation existed):

```
$ npx vitest run src/features/log/LogPage.test.tsx src/lib/time.test.ts src/components/navModel.test.ts
 ❯ src/features/log/LogPage.test.tsx (0 test)
   Error: Failed to resolve import "./LogPage" from "src/features/log/LogPage.test.tsx"
 ❯ src/components/navModel.test.ts (4 tests | 1 failed | 3 skipped)
   × visibleNavGroups > shows the Log entry to every staff role
     → expected undefined to be truthy
 ❯ src/lib/time.test.ts (14 tests | 3 failed | 11 skipped)
   × dayKey > returns the viewer local calendar day as YYYY-MM-DD
     → dayKey is not a function
   × dayKey > keys two timestamps on the same local day the same...
     → dayKey is not a function
   × dayKey > keys timestamps on either side of local midnight differently
     → dayKey is not a function
 Test Files  3 failed (3)
      Tests  4 failed | 14 skipped (18)
```

GREEN (after implementing `dayKey`, `LogPage.tsx`, the icon, nav entry and route):

```
$ npx vitest run src/features/log/LogPage.test.tsx src/lib/time.test.ts src/components/navModel.test.ts
 ✓ src/components/navModel.test.ts (4 tests)
 ✓ src/lib/time.test.ts (14 tests)
 ✓ src/features/log/LogPage.test.tsx (7 tests)
 Test Files  3 passed (3)
      Tests  25 passed (25)
```

Full suite after that (before fixing the two pre-existing nav-list assertions):

```
Test Files  2 failed | 63 passed (65)
     Tests  2 failed | 641 passed (643)
```
(`AppShell.test.tsx` and `CommandPalette.test.tsx` — both hardcoded item-list assertions
that didn't yet include "Log".)

After updating those two assertions:

```
$ npm test
 Test Files  65 passed (65)
      Tests  643 passed (643)
```
632 (baseline) + 11 new tests (7 LogPage + 3 dayKey + 1 navModel) = 643. Matches exactly.

```
$ npm run lint
> eslint src --ext .ts,.tsx
(clean, no output)

$ npm run build
> tsc -b && vite build
✓ 171 modules transformed.
✓ built in 2.92s
```

## Sabotage verification

Each break was applied, confirmed to fail the specific test, then reverted before moving
to the next.

1. **Tab strip / selected.** Changed `aria-selected={true}` → `aria-selected={false}` in
   `LogPage.tsx`. `renders a tab strip whose only tab is Posts, and it is selected` failed
   (`Expected aria-selected="true", Received aria-selected="false"`). Reverted.
2. **Day grouping.** Changed the run-continuation check in `groupByDay` from
   `if (current?.key === key)` to `if (false)`, forcing every entry into its own group.
   `groups entries under day headings...Today · 2 posts` failed (rendered two
   `Today · 1 post` headings instead of one `Today · 2 posts`). Reverted.
3. **Pinned block conditional.** Changed `{pinned.length > 0 ? (...` to `{true ? (...`,
   rendering the "Pinned" section unconditionally. `omits the pinned block entirely when
   pinned is empty` failed (found the "Pinned" heading it shouldn't have). Reverted.
4. **Shift filter wiring.** Changed `shift: shift || undefined` to a hardcoded
   `shift: undefined` in the `useLogFeed` call. `issues a request with shift=overnight
   when the shift filter changes` failed (timed out waiting for a request containing
   `shift=overnight` — the selection never reached the query). Reverted.
5. **Mentioning-me wiring.** Changed `mentioningMe` to a hardcoded `mentioningMe: false`
   in the `useLogFeed` call. `issues a request with mentioningMe=true when the Mentioning
   me toggle is checked` failed the same way. Reverted.
6. **Empty state.** Changed the empty-feed branch condition from
   `pinned.length === 0 && groups.length === 0` to `false`, so an empty feed fell through
   to the (empty) groups-rendering branch. `renders an empty state, not a bare page, for
   an empty feed` failed (rendered an empty `<div class="flex flex-col gap-4 p-4" />`
   instead of the "No log entries yet" message — i.e., a bare page). Reverted.
7. **dayKey local-vs-UTC.** Changed `dayKey` to use `getUTCFullYear`/`getUTCMonth`/
   `getUTCDate`. Two of the three `dayKey` tests failed (`keys two timestamps on the same
   local day...` and `keys timestamps on either side of local midnight...` — both off by
   one day on this dev machine, which trails UTC). The third (`returns the viewer local
   calendar day...`, using a mid-morning timestamp) happened to still pass since it isn't
   near a day boundary — expected, and covered by the other two. Reverted.
8. **Nav gating.** Changed the Log nav item's `needs: []` to `needs: ['manage_admin']`.
   `shows the Log entry to every staff role` failed (`expected undefined to be truthy` —
   `visibleNavGroups(() => false)` filtered it out). Reverted.

After each revert, the specific test file was re-run to confirm it passed again before
moving to the next sabotage; the full suite/lint/build were re-run at the end (see above)
to confirm the working tree matches the GREEN state.

## Files changed

- `web/src/features/log/LogPage.tsx` (new)
- `web/src/features/log/LogPage.test.tsx` (new)
- `web/src/lib/time.ts` (added `dayKey`)
- `web/src/lib/time.test.ts` (added `dayKey` tests)
- `web/src/components/NavIcon.tsx` (added `log` icon)
- `web/src/components/navModel.ts` (added Log nav item)
- `web/src/components/navModel.test.ts` (added the brief's `visibleNavGroups` test)
- `web/src/routes.tsx` (added `LogPage` import and `/app/log` route)
- `web/src/components/AppShell.test.tsx` (updated hardcoded item list — pre-existing test,
  not authored by this task, but its expectation was stale after adding the nav entry)
- `web/src/components/CommandPalette.test.tsx` (same, for the command palette's option
  list)

Commit: `d557733 feat(web): assemble the hotel log page` on branch `hotel-log`.

## Self-review findings

- Confirmed `server/data/app.db*` was not staged or committed (only the 10 files above
  were `git add`ed explicitly; `git status` was checked before and after `git add` to
  verify nothing else slipped in).
- `server/app/domain/users.py`'s working-tree modification was left untouched, per the
  brief's note that it's a line-ending artifact.
- `two.png` deletion, `.claude/`, and `images/` are pre-existing/unrelated working-tree
  state, not touched.
- Verified the tab strip is a real `role="tablist"`/`role="tab"` pair (not a styled div),
  so a later Wakeups/Followups tab can be added without restructuring.
- Verified no `RequireCapability` wrapper was added around the `log` route, and the nav
  item's `needs` is `[]` — both per the "things the brief cannot tell you" section.
- Double-checked `LogFeedParams.shift`/`departmentId` are `string | null | undefined`,
  so passing `shift || undefined` for an empty-string select value is correct (an empty
  string is falsy, so "All shifts" cleanly omits the param).
- The department select's `id`/department options double as both the page's own filter
  and reuse the same `useDepartments()` query already used internally by `LogComposer` —
  confirmed via the test's `fetch` mock that only one `/departments` request pattern is
  needed (same query key, cached).
- `dayHeading` for non-today days uses `toLocaleDateString([], { weekday: 'long', month:
  'long', day: 'numeric' })`; the brief only specifies the "Today" format, so this is a
  reasonable, unspecified default. Flagging it as a judgment call, not a tested contract.

## Concerns

- None blocking. The two pre-existing test updates (AppShell, CommandPalette) are
  necessary consequences of a `needs: []` nav item, not scope creep, but I'm flagging them
  explicitly since they weren't listed as files to modify in the brief.
- The non-"Today" day-heading format (full weekday/month/day) is untested and unspecified
  by the brief — worth confirming against the mockup/spec §7 if a reviewer wants an exact
  string, though nothing in Task 13's scope requires it.
