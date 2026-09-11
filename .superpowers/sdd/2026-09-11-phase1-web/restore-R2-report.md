# Restoration R2 — report

Branch `main`, started from `989ab7c`. Six commits, in this order (two `docs:` commits from
another process in the tree landed interleaved; they are not mine):

| sha | item |
|---|---|
| `7323e9c` | server: pre-flight port guard + zero-socket broadcast warning |
| `4ceeadd` | R2.0 — board filter row is single-select |
| `bd66fc1` | R2.1 — reveal verified and cancelled work orders |
| `8208dd8` | extra item — rail entry stays lit across a whole section |
| `aab49e8` | R2.2 — raise a work order with no conversation |
| `7640b04` | R2.3 — standalone comment on a work order |

## Verification

```
web:    52 files, 539 passed, 0 failed   (baseline 51 / 520 — +19 tests, none broken)
        npx tsc -b clean · npm run lint exit 0 · npm run build clean
        npm test 2>stderr: stderr is 0 bytes. No React warnings anywhere in the output.
server: 347 → 348 passed (one added), ruff clean
```

No `.d.ts` under `web/tests/` — the only generated ones live in `web/.tsbuild/`, the
declaration out-dir, which is gitignored. Playwright E2E not run, as instructed.

Every production change was mutation-tested: reverted in turn, confirmed the suite goes red,
restored. The mutations and the tests that caught them are listed per item below.

Verified in the running app (Vite on 5173 against the already-running API on 5200 — I did not
start a second server), as `alex@hvh.test`, in both themes. Dark was checked by setting
`documentElement.dataset.theme` directly, never through the UI toggle.

---

## R2.0 — the board's filter row is single-select (the user-reported defect)

`docs/mockups/Board.dc.html:59-63` draws five `.tab`s with exactly one `.on`. The shipped board
built them as three independent URL filters (`mine`, `dept`, `urgent`) that combined freely, so
"Mine + Engineering" lit two tabs.

Picking a tab now deletes the other two params. The *rendered* selection is also derived from the
params through one precedence (`mine` → `dept` → `urgent` → All), so a link that still carries two
filters lights one tab rather than two. That second half matters: clearing on write alone would
still show the reported symptom to anyone opening an old bookmark or a pasted URL.

The three params stay separate rather than collapsing into one `?filter=`, so `landingPath`'s
`?mine=1` for dept_staff and supervisors keeps working. Checked in the app: `/app/board?mine=1`
lands with Mine lit and requests `mine=true`. `All` still deletes only `mine`/`dept`/`urgent`,
preserving `view=list` (and now `closed=1`).

**What this removes — please read.** Two combinations were genuine behaviour and now have no
control at all:

- **"mine and urgent"** — my urgent work only.
- **"mine within a department"** — e.g. my Engineering work orders.

(`dept` + `urgent` was also reachable and is gone too.) I have not invented a replacement, because
single-select is what you asked for and what the mockup draws. If any of these are missed, the
natural restoration is a secondary control — an "Urgent only" checkbox beside the row, or a
department dropdown — rather than going back to freely-combining tabs.

One deliberate behaviour choice: clicking the already-selected tab does **not** deselect it. With
`role="tab"`/`aria-selected`, a selected tab that turns itself off on a second click is wrong for
assistive tech, and `All` is the explicit "no filter" tab.

Tests: `lets only one filter tab be selected at a time`, `lights exactly one tab even when a stale
URL still carries two filters`. Mutation: restored the original `BoardPage.tsx` from HEAD — both
fail, the rest of the file's 9 tests pass.

## R2.1 — verified and cancelled work orders

**Rendering choice: two terminal board columns, and matching groups in the list view.** Not a
single "Closed" column: `verified` and `cancelled` are different outcomes, and the reviewer this
feature exists for ("what did we verify this week?") needs to tell them apart. `WorkOrderCard`
renders no status, so mixing closed rows into the flat list view would have made them
indistinguishable from open work — hence the same two labelled groups there, appended under the
active list. The five open columns absorb nothing.

The footer control matches the mockup's wording and placement: muted "Verified and cancelled
hidden ·" with an accent-coloured action. It drives `?closed=1`, which is passed to
`useWorkOrders({ includeClosed })`, so the reveal is a real refetch, survives a reload, and is
linkable. The footer renders on every state including the empty state, so the reveal is always
reversible.

**Count.** The mockup's "46 closed this week" is not rendered. The query applies no week window,
so claiming one would be a lie; the revealed state reads "Showing *N* verified and cancelled" with
N being the number of closed rows actually returned. Live check on seed data: 6 verified, 0
cancelled, footer said "Showing 6", and the header's "29 active · 3 urgent" did not move — the
active and urgent counts are computed over open statuses only, so revealing closed work cannot
inflate them.

Colour: the mockup tints that action with `var(--roomNum)`. I used `text-accent` instead, per the
brief's "blue = accent/primary action" rule; `--roomNum` is the room-number token and both are
blue in both themes. Say the word if you want the mockup's exact token.

Tests: `hides verified and cancelled work until the footer control reveals them` (asserts the
fetch changes, the rows render, the columns exist, the count is real, the active count does not
move, and the Complete column does not absorb them), `round-trips the reveal through the URL`,
`groups the revealed closed work by outcome in the list view too`, `keeps the reveal when All
clears the filters`. The test mock now withholds closed rows unless `includeClosed=true`, the way
the real server does — without that the toggle would have "passed" while fetching nothing new.
Mutations: dropping `includeClosed` (4 fail) and pinning the columns back to `BOARD_COLUMNS`
(3 fail).

## R2.2 — raise a work order with no conversation

`conversationId` is optional. Absent: the prefill query is never enabled (no placeholder id is
invented), and the form opens blank immediately rather than sitting on the prefill spinner.

The POST body **omits** `sourceConversationId` and `sourceMessageId` rather than sending null. The
schema would accept null (`str | None`) and the route branches on truthiness, so null would also
work — omission is just the honest shape, and the test asserts the keys are absent.

**One addition the brief implies and I want flagged: a Location type select.** The form had no
control for `locationType`; it always sent `room`. That was invisible while every work order came
from a guest conversation whose prefill chose the type, but the mockup's standalone examples are
POOL PUMP, 3F ICE and ELEV B — all `equipment`, none a room. Without the control every standalone
work order would be filed with wrong location data. The brief's "every field the prefill would
have filled must be editable" covers it, since `locationType` is one of those fields.

The **New** button is gated on `can('create_work_order')` (excludes corporate) and sits in the
header where the mockup puts it. The modal is mounted only while open because it needs a
`ToastProvider` — the same pattern `Composer.tsx` uses and for the same reason.

The conversation-attached path is untouched and **all seven of its existing tests pass
unmodified**; I changed none of them.

Note for the reviewer: `BoardPage` now imports `CreateWorkOrderModal` from `features/inbox/`. It is
the same modal, and moving it to a shared location would have churned four files for no behaviour
change — but it is now genuinely shared, so a later move is reasonable.

Tests: `opens blank with no conversation and asks the server for no prefill`, `posts a standalone
work order without a sourceConversationId key`, `will not save an empty title with no conversation
either`, plus `raises a work order from the header with no conversation behind it` and `hides New
from a role without create_work_order` on the board. Mutation: reverting the blank-form seeding —
4 fail.

## R2.3 — standalone comment

Textarea plus a Comment button in its own section under the Timeline, as
`WorkOrder.dc.html:130-131` places it. PATCHes `{ comment }` alone. Disabled for empty or
whitespace-only input; clears on success. `usePatchWorkOrder` already invalidates
`qk.workOrder` (the detail) and `qk.workOrdersAll` — the latter is the `['workOrders', propertyId]`
prefix, so it covers every board query variant including the new `includeClosed` ones — and the
source conversation when there is one. No new invalidation was needed; I checked the other
readers rather than assuming.

**Brief correction: there is no capability to gate this on.** The brief says "gate it on the
capability the server actually enforces for this route." `PATCH /work-orders/<id>` carries
`@require_auth` and `@require_property` and nothing else; its only capability check is
`close_work_order`, and only for closing *statuses*. The standalone comment branch enforces
nothing. So the faithful client is ungated, and that is what I built. `add_note` would have been a
guess, and it is held by all six roles anyway, so gating on it would have been decorative.

Related observation, **not fixed** (pre-existing, out of scope for a web wave, flagging it rather
than silently changing server auth): that same PATCH route lets any authenticated member of the
property reassign and reprioritise a work order with no capability check. `corporate` — which has
neither `reply` nor `create_work_order` — can therefore mutate work orders through the API. Worth
a server-side decision.

Tests: `posts a standalone comment and shows it in the timeline` (asserts the body is comment-only,
the box clears, and the note appears in the Timeline after the refetch), `will not post an empty or
whitespace-only comment`. The detail test mock is now stateful across a PATCH, so "appears in the
Timeline" is a real round trip rather than a re-render of the original fixture. Mutations: removing
`<CommentBox>` (2 fail) and changing the guard from `trim()` to raw length (1 fail).

---

## The pre-flight guard (its own commit, `7323e9c`)

`server/dev_start.py` now probes `127.0.0.1:<port>` before doing any work and exits non-zero with
an explanation if anything answers. Two API processes silently break realtime delivery:
`realtime/registry.py` is a per-process dict, so the browser's socket can live in process A while
the delivery job is claimed by process B's worker, which broadcasts into an empty registry.
Werkzeug sets `SO_REUSEADDR`, so on Windows the second bind reports nothing at all.

Deviations from the brief's sketch, both deliberate:

- Placed **before** `prepare()` rather than immediately before `app.run()` at the named anchor, so
  a doomed start does not run migrations and a seed check against a database another process is
  using. Still the last thing before the server would have come up.
- Skipped when `WERKZEUG_RUN_MAIN=true` — the reloader child, which its own parent already vetted.
  The parent never binds the port, so this is belt-and-braces rather than a fix for a real race,
  but it removes any chance of a confusing false positive on reload.

Paired with it: `realtime/broadcast.deliver()` no longer discards `ConnectionRegistry.send`'s
delivered count. Zero deliveries now logs a WARNING naming the event, the property and the number
of sockets this process holds for it — which is what distinguishes "nobody is logged in" from
"wrong process". Be aware this will be chatty on a quiet dev instance; that seemed better than the
silence that cost a diagnosis wave.

Test added: `test_port_is_taken_detects_a_listening_socket_and_a_free_port` (binds a real ephemeral
socket, asserts both directions). Server suite 347 → 348.

**I did not start a server.** One was already listening on 5200 when I began; I used it, and the
Vite dev server already running on 5173, for all manual verification.

## Extra item — the Admin rail pill (its own commit, `8208dd8`)

The rail entry navigated to `/app/admin/users` and React Router's `isActive` matches only `to` and
its descendants, so `/app/admin/departments` — a sibling — left the pill unlit.

`NavItem` gained an optional `match?: string[]`; `isNavItemActive(item, pathname)` compares whole
path segments (`pathname === prefix || pathname.startsWith(prefix + '/')`), so `/app/administration`
can never light Admin. `AppShell` computes the active state from the current location instead of
taking `isActive` from the render prop. `to` is unchanged, so clicking Admin still lands on Users &
roles, as the index redirect does.

Two departures from your instructions, both flagged:

1. **`match` is `string[]`, not `string`.** Because there *is* a second entry with the same shape,
   and a single prefix cannot express it: a work order opens at `/app/work-orders/:id`, a sibling
   of `/app/board`, so the **Board** pill went dark the moment you opened a card. Board now carries
   `match: ['/app/board', '/app/work-orders']`. Inbox (`inbox` + `inbox/:id`), Alerts and Analytics
   are true section roots with descendant children and need no `match` — verified against
   `web/src/routes.tsx` rather than assumed.
2. **`NavLink` is now a plain `Link`.** Its only contribution was the `isActive` we no longer use,
   and it could not have set `aria-current` for the very case it got wrong (NavLink only emits
   `aria-current` when its own matcher says active). The shell sets `aria-current="page"` from the
   computed state, which is what the existing test asserts and what screen readers need.

The command palette needed nothing: it shares `visibleNavGroups` but only navigates to `item.to`,
which is unchanged — confirmed in `CommandPalette.tsx`, and its 15 tests pass. Its Admin entry
still goes to `/app/admin/users`.

Verified in the browser as `alex@hvh.test` across all six sub-nav screens — Users & roles,
Departments, Quick replies, Digital assets, Resolution categories, Property settings — the pill's
computed background is `rgb(37, 99, 235)` and `aria-current="page"` on every one, and neither on
`/app/board` or `/app/analytics`. Screenshot of Departments with the pill lit:
`.superpowers/sdd/2026-09-11-phase1-web/admin-rail-departments-lit.png`.

Tests: `keeps the Admin rail entry lit on every screen inside the section`, `does not light the
Admin entry from outside the section`, `keeps Board lit on a work order, which lives outside
/app/board`, plus a new `navModel.test.ts` covering the segment boundary (`/app/administration`,
`/app/boardroom`) and the no-`match` fallback. Mutation: removing both `match` fields — 3 fail.

---

## Anchors checked

Two line numbers in the brief had drifted; the rest held.

| brief | actual |
|---|---|
| `server/app/api/work_orders.py:98` (`include_closed`) | line **28** |
| `server/app/api/work_orders.py:87` (`elif p.comment`) | line **86** |
| `server/app/schemas/work_orders.py:25` | correct |
| `docs/mockups/Board.dc.html:69` / `:174` | correct |
| `BoardPage.tsx:86-93` (the tab row) | correct |

## Things to know

- **The tree has another writer.** Two `docs:` commits (`e9282f7`, `0718721`) landed between mine
  during this wave, and the working tree also shows a `two.png` deletion and new `correct.png` /
  `incorrect.png` that are not mine. I staged only my own files, never `git add -A`, so none of
  that is in my commits. `server/data/app.db*` is tracked and is being modified by the running
  server; I left it dirty rather than committing it.
- **Changing `Mine`/`dept` flips the board through its full-page pending spinner**, because it is a
  new query key with no cached data, and the whole header unmounts with it. Pre-existing, not
  touched — but it is why the new tests re-query each tab after every click, and it is a visible
  flash a user might report next. `placeholderData: keepPreviousData` would fix it.
- No hardcoded hex was added anywhere; everything new uses existing tokens.
