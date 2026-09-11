# Task 21 report — End-to-end tests, production build and README

**Status:** DONE_WITH_CONCERNS
**Commit:** `336d9ad` test(web): Playwright smoke and presence specs, and document the web client

---

## What I implemented

| File | Change |
|---|---|
| `web/playwright.config.ts` | new — runner config, two `webServer` entries (Flask on 5200, Vite on 5173) |
| `web/tests/e2e/smoke.spec.ts` | new — the §7 full loop: guest text → agent reply → delivered → work order → completion → draft prompt → guest |
| `web/tests/e2e/presence.spec.ts` | new — §11.1 #3, two agents on one conversation |
| `README.md` | new **Web client** section (+ the three sub-sections), one line added to the seeded-logins note |
| `web/src/routes.tsx` | **unchanged** — correction #3 confirmed: there is no `Placeholder` component in the file, and nothing in `web/src` references that name |

`@playwright/test` and the `test:e2e` script were already present; nothing was added to
`package.json`. `web/.gitignore` already ignores `playwright-report/` and `test-results/`, and
`tsconfig.node.json` already lists `playwright.config.ts`, so `tsc -b` type-checks the new config.

### The four dispatched corrections

1. **Port 5200** — applied in both places (`webServer.url`, README proxy sentence).
2. **No `server/.env`** — none created; the `Delivered` failure I hit was diagnosed from
   `dev_start.py`'s own output plus the job table, not from an env file (see Findings).
3. **`Placeholder`** — confirmed absent; no deletion invented.
4. **README block reconciled** — see "README deltas" below.

### Deviations from the brief's sample code (all deliberate, all diagnosed)

Six changes. Four of them are fixes for assertions that were either broken or green-for-the-wrong-reason; none weakens what the spec proves.

1. **`workers: 1` added to the config.** `fullyParallel: false` only serialises tests *within* one
   file — separate spec files still get separate workers. Both specs sign in as Ava, and server
   presence is keyed by user id (`PresenceStore._where: user_id -> conversation_id`), so two
   concurrent Ava sessions would move each other's presence entry between conversations. This
   implements the brief's own stated intent ("one server, one database — parallel specs would
   fight over seed state"); the comment as written did not achieve it.
2. **`MARKER` is base 36, not the raw epoch.** `Date.now()` is a 13-digit run; §9.1's card
   redaction masks any 13–19 digit run that passes Luhn (`server/app/domain/redaction.py`). The
   very first full run failed on exactly this: the marker `e2e-1789136828768` arrived as
   `The AC is broken e2e-**** **** **** 8768`. Roughly one run in ten would have failed.
   The app behaved correctly; the sample marker was flaky.
3. **Thread assertions scoped to bubbles, not to the page.** `getByText(GUEST_TEXT)` /
   `getByText(replyText)` would have been strict-mode violations: at desktop width the queue list
   and the thread are both on screen, and `last_message_preview` is the message body verbatim to
   140 chars (`server/app/domain/conversations.py:169`). Now `getByTestId('bubble').filter(...)`.
4. **`Delivered` scoped to the reply's own bubble row.** The brief's
   `getByText('Delivered').first()` is green before the test does anything — Sarah's seeded thread
   already contains delivered messages. Now
   `getByTestId('bubble-row').filter({hasText: replyText}).getByText('Delivered')`. This is a
   strengthening: the original assertion could not fail.
5. **Draft-prompt locators scoped to this run's work-order title.** The brief's
   `sms-in.filter({hasText: draftText.slice(0, 30)})` matched *two* elements on the second
   consecutive run — every run's draft starts "Hi Sarah — our team has taken care of…", and only
   the quoted WO title carries the marker. Now the filter is the whole `draftText`, and both the
   banner locator and the final `toHaveCount(0)` are scoped to `woTitle`, so a run that dies
   mid-way and leaves a pending prompt cannot break the next run.
6. **Presence: `a[href^="/app/inbox/"]`, not `getByRole('link').first()`.** The left nav's own
   links (`/app/inbox`, `/app/board`, …) come first in the DOM, so `.first()` clicked the *nav*,
   not a queue row. Nothing in the spec depends on *which* conversation it lands on.

The presence regex was checked against the component, per the dispatch: `presenceLine()` in
`web/src/features/inbox/ConversationHeader.tsx:11` is fed `others.map(u => u.firstName)` and
renders `"Marcus is viewing"` / `"Marcus is replying"`. The brief's regex is correct as written —
**first** name, not full name.

I also corrected the presence spec's trailing comment: a hard `page.goto` drops the socket and the
server clears the user in `ws_route`'s `finally`; the 10s sweeper is the backstop for a connection
that dies silently, not the mechanism this assertion exercises.

---

## What I tested, and the results

### Step 4 — the E2E suite

```
$ cd web && npx playwright install chromium
Chrome Headless Shell 153.0.8010.12 ... downloaded

$ npm run test:e2e
Running 2 tests using 1 worker

  ✓  1 tests\e2e\presence.spec.ts:13:1 › two agents on one conversation each see the other within 2 seconds (3.5s)
  ✓  2 tests\e2e\smoke.spec.ts:18:1 › a guest text becomes a reply, a work order, and a closed loop (7.7s)

  2 passed (15.8s)
```

Run **three consecutive times** against an accumulating database (15.8s / 15.1s / 15.5s), all green.
Repeat runs were the point: the second run is what exposed deviation #5.

### Step 5 — production build and the simulator exclusion

```
$ npm run build
> tsc -b && vite build
✓ 146 modules transformed.
dist/index.html                   0.75 kB │ gzip:  0.43 kB
dist/assets/index-xmz7JYUZ.css   17.95 kB │ gzip:  4.83 kB
dist/assets/index-qY__xNaC.js   300.02 kB │ gzip: 90.36 kB
✓ built in 1.92s

$ node -e "...includes('Phone simulator')..."
simulator excluded from 2 asset files
```

`import.meta.env.DEV` gating in `routes.tsx` holds: Rollup drops the lazy import entirely, and the
whole app is one 300 kB chunk with no simulator chunk at all.

### Step 5 — the rest of the suite

| Command | Result |
|---|---|
| `cd server && python -m pytest -q` | **256 passed** in 23.06s |
| `cd web && npm test` | **43 files / 358 tests passed** |
| `cd web && npx tsc -b` | clean |
| `cd web && npm run lint` | **fails** — `ESLint couldn't find a configuration file` |

The lint failure is the known pre-existing gap the dispatch named: there is no ESLint config in
this repo and `npm run lint` has never worked. I did not create one — out of scope, and already on
the controller's list. I did type-check both specs out-of-band (`tsc --noEmit --strict` over the two
files): clean. Note that `tests/` is in no `tsconfig` `include`, so `tsc -b` does **not** cover the
specs; Playwright transpiles them without type-checking. Adding `"tests"` to `tsconfig.json` would
close that, but it is outside this task's file list.

---

## Step 7 — the §10 acceptance list, item by item

> `python -m venv`, `pip install -e "server[dev]"`, `npm install`, `npm run seed`, then both dev servers — brings up both surfaces on a clean machine

**PARTIALLY VERIFIED.** I did **not** perform a clean-machine bring-up: I did not delete and rebuild
the venv, and did not re-run `pip install` or `npm install` from empty. What I did verify on this
machine:
- `npm run seed` (as `python -m seed.seed`) runs clean and rebuilds the database from scratch:
  `SeedSummary(properties=2, users=14, guests=106, stays=106, conversations=30, messages=52, work_orders=21)`.
- Both dev servers come up and serve both surfaces — Playwright started `python ../server/dev_start.py`
  and `npm run dev` itself on every run, and drove real screens on both.
- Every command the README names exists: root `seed` / `server` / `schema` / `test:server`, and
  `web`'s `dev` / `build` / `test` / `test:e2e` / `gen:types`.

One caveat that a clean machine *will* hit and which the README now states: `npm run test:e2e`
shells out to `python ../server/dev_start.py`, so the venv must be active — a bare `python` on this
machine resolves to a global 3.14 that has Flask but not the `app` package, and the API would never
start.

> all server tests pass, including the §11.1 suite

**VERIFIED.** 256 passed, 0 failed.

> the Playwright smoke passes

**VERIFIED.** Passes, and passes repeatedly (3 consecutive runs).

> every screen in §5.2 is reachable by the roles that should see it and hidden from the ones that should not — check all six seeded roles

**VERIFIED**, live in a browser. I drove all six seeded roles through a throwaway spec (run, recorded, then deleted — not committed):

| Role | Landing | Nav | `/app/analytics` | `/app/admin/users` |
|---|---|---|---|---|
| agent (ava) | `/app/inbox` | Inbox, Board, Alerts | → `/app/inbox` (bounced) | → `/app/inbox` (bounced) |
| dept_staff (eli) | `/app/board?mine=1` | Inbox, Board, Alerts | → `/app/board` (bounced) | → `/app/board` (bounced) |
| supervisor (sam) | `/app/board?mine=1` | Inbox, Board, Analytics, Alerts | reachable | → `/app/board` (bounced) |
| manager (morgan) | `/app/analytics` | Inbox, Board, Analytics, Alerts | reachable | → `/app/analytics` (bounced) |
| admin (alex) | `/app/analytics` | Inbox, Board, Analytics, Alerts, Admin | reachable | reachable |
| corporate (casey) | `/app/analytics` | Inbox, Analytics, Alerts, Admin | reachable | reachable |

`/app/inbox` and `/app/notifications` are reachable by all six, as intended. Two observations, neither
introduced by this task:
- **Corporate can reach `/app/admin/users`.** §5.2's table note says "Admin only", but
  `capabilities.ts` gives `manage_admin` to `['admin', 'corporate']`, deliberately mirroring the
  server's `permissions.py`, and `capabilities.test.ts` asserts it. The client matches the server;
  the spec's one-word note is the thing that is out of step.
- **The Board is hidden from corporate in the nav but is not route-gated** — corporate can reach
  `/app/board` by typing the URL. That is consistent with the server, which documents work orders
  as property-wide with no viewing capability (`work_orders.py` `detail()` docstring).

> the README documents setup, seeded credentials, the simulator and the Postgres switch

**VERIFIED.** Setup (existing) + the new Web client section; the seeded-logins table with the shared
password; "The phone simulator"; "Moving to PostgreSQL" (existing).

---

## README deltas from the brief's block (correction #4)

Everything I wrote was checked against the actual scripts and code:

- **`127.0.0.1:5200`** in the proxy sentence (the brief said 5000).
- **`/a/<short-code>`**, not `/a` — `vite.config.ts:52` proxies the regex key `^/a/`, deliberately
  so that `/app/*` is *not* proxied. Writing "`/a`" in the README would describe the bug that key
  was written to fix.
- **`127.0.0.1`, not `localhost`, throughout** (dev URL, `/sim`, the login URL). `vite.config.ts:43`
  pins `host: '127.0.0.1'` with a comment about exactly this: on Windows `localhost` can resolve to
  `[::1]` and be refused.
- **"`npm run server` from the repo root"** — the script lives in the root `package.json`, not in
  `web/`, and the table's commands run from `web/`. The brief's text was ambiguous about which.
- **Added**: the venv requirement for `npm run test:e2e`, and the one-time
  `npx playwright install chromium`. Both are things a new machine fails on; I hit the first myself.
- Every claim verified to exist: `server/tests/test_schema_export.py`, `src/api/types.generated.test.ts`,
  `PATCH /api/auth/prefs` (`app/api/auth.py:86`), the `0000` / `30007` failure path
  (`app/channels/mock_sms.py:17-18`), `engines.node >= 20`.
- The seeded-logins note got one sentence, per the brief's "extend the seeded-logins table note".

---

## Findings about the app (not fixed — reporting, per the dispatch)

### 1. The dev database had exploded to 826 MB; outbound SMS was starved and never delivered

This is what the first smoke run actually failed on, and it is worth the controller's attention.

`server/data/app.db` was **826,302,464 bytes**. The job table held:

```
sla.sweep    done    2,736,186
sla.sweep    queued     46,395
sla.sweep    running        13
snooze.wake  done       27,985
outbound.send queued         6     <-- starved
```

`jobs.claim_due()` takes the 20 oldest due jobs (`order_by(Job.run_at).limit(20)`), and ~46k
ancient `sla.sweep` rows sat permanently in front of every new `outbound.send`. So **no outbound
message ever left `queued`** — the thread showed four staff/automation replies stuck at "Sending…",
including the STOP/START/HELP auto-replies from what looks like Task 20's manual session. The
feature was broken on this machine, silently, before I arrived.

**Mechanism.** `jobs.claim_due()` uses `.with_for_update(skip_locked=True)`
(`server/app/queue/jobs.py:29`). **SQLite has no `SELECT … FOR UPDATE`**; SQLAlchemy's SQLite
dialect drops the clause silently. So the claim is not exclusive. If two worker processes ever run
against the same file — two `dev_start.py`/`run.py`/`start.bat` instances, which is easy to do
accidentally — both can claim the same recurring job, both call
`schedule_next_recurrence()`, and every recurring job **doubles** each interval. 2^16 ≈ 65k, and
`sla.sweep` runs every 30 s: roughly eight minutes of overlap produces exactly the numbers above.
The worker-start gating itself is correct (`app/__init__.py:113` — reloader child only, one worker
per process); it is two *processes* that break it.

Not in this task's scope to fix, and it does not reproduce with a single server: after reseeding,
three full E2E runs left exactly one queued row per recurring type and a 557 kB database. But
Phase 1 ships SQLite as the default, `README` tells people to double-click `start.bat`, and this
failure mode is silent (messages just never send) and unbounded on disk. Worth a follow-up.

**What I did about it:** backed up the 826 MB database to
`…/scratchpad/app.db.bak` and ran `npm run seed` to recreate it. The database is gitignored dev
seed data, the README documents `npm run seed` as "wipes and recreates", and the specs are defined
to run against seed data — but it was still destructive of whatever manual state was in there, so
it is called out here rather than buried. The backup is in the session scratchpad if anything in it
mattered.

### 2. Presence is not cleared by an in-app navigation away from a conversation

`ConversationView`'s unmount calls `setPresence(null, 'viewing')`, but `setPresence` in
`web/src/api/ws.ts:129` only sends a frame `if (conversationId)` — a null never reaches the wire.
Meanwhile the client heartbeats every 5 s unconditionally, and the server's `heartbeat` branch calls
`presence.store.touch(user_id)`, which refreshes the entry for whatever conversation the user is
still recorded in. So clicking **Board** in the left nav (a client-side `NavLink`) leaves
"Ava is viewing" on that conversation for everyone else **indefinitely** — the 10s sweeper never
fires, because the heartbeat keeps resetting the clock.

The server already supports the fix: `ws.py`'s `presence` branch handles a null `conversationId` by
calling `store.update(None, …)`, which clears the user and broadcasts. Only the client's one-line
guard prevents it being used.

My presence spec does **not** hide this: it uses `page.goto`, a hard navigation, which tears down
the socket, so the server's disconnect path clears presence and the assertion is honest about what
it exercises (I rewrote the comment to say so). A spec that exercised in-app navigation would fail
today. I did not write one, because fixing Task 13's component is outside this task; flagging it
instead.

### 3. Noisy dev-server output (cosmetic)

Every closed WebSocket makes Vite log a stack trace: `[vite] ws proxy socket error: Error: write
ECONNABORTED`. The proxy works (presence would fail otherwise) — it is Vite's proxy complaining
about a socket the browser has already closed. It makes `npm run test:e2e` output much noisier than
it needs to be. Pre-existing; not touched.

---

## Self-review

- **Completeness.** All eight steps done. Step 5's `Placeholder` deletion was a no-op (confirmed,
  not invented). Step 7 walked honestly, including the one item I could only partially verify.
- **Quality.** Every deviation from the brief carries a comment in the file saying *why*, so the
  next reader does not "restore" the sample code and reintroduce the flake. Locators are marker-
  scoped or test-id-scoped throughout; no index-based or ordering-based assertion survives except
  "any conversation row" in the presence spec, where nothing downstream depends on which.
- **Discipline.** Nothing added beyond the brief's file list. No ESLint config. No `package.json`
  edits. No production code touched — both findings above are reported, not fixed.
- **Testing.** The specs exercise real behaviour end to end: the mock SMS wire, the job worker, the
  WebSocket, the prefill endpoint, the transition state machine, the draft-prompt lifecycle, and
  presence across two browser contexts. I deliberately strengthened the two assertions that could
  not fail (`Delivered`) or that passed on stale state (the draft filter) — and I weakened nothing.
  No timeout was loosened.
- **Output.** Test output is clean. Server/Vite log noise is described above and is pre-existing.

## Concerns

1. Finding #1 is a real, silent, unbounded production-adjacent bug (SQLite + `skip_locked`). It
   cost me a full debugging cycle on this task and will cost the next person more.
2. Finding #2 means presence is quietly wrong during ordinary in-app navigation, which is the
   common case — the E2E spec passes because a hard navigation happens to take the honest path.
3. The specs are not covered by `tsc -b` (no `tests` in any tsconfig `include`).
4. `npm run lint` remains broken repo-wide.
