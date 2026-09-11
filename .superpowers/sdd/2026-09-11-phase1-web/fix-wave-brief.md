# Final fix wave — Phase 1 web branch

Every item below is a CORRECTION. Do them all, in this order. Nothing here is new feature
work; the five feature restorations the final review raised (I1/I4/I5/I6/I9) are deliberately
NOT in this wave and are not yours to build.

Repo root: `C:\Users\bryan.farrell\Downloads\messaging_app_nw`. Branch `main`, HEAD `336d9ad`.

---

## 1. Defect A — presence sticks forever on in-app navigation (client, one line)

`web/src/api/ws.ts:128-134` records `lastPresence` unconditionally but SENDS only
`if (conversationId)`, so `ConversationView.tsx:28`'s unmount `setPresence(null, 'viewing')`
never reaches the wire. The unconditional 5 s heartbeat (`ws.ts:214`) keeps refreshing
`seen_at` server-side (`server/app/realtime/ws.py:77-78` → `presence.py:68-73`), so
`sweep()` (`presence.py:50-61`) never expires the entry. Result: "Ava is viewing 412" while
Ava is on the Board, forever.

It only bites when leaving the inbox ENTIRELY. Conversation-to-conversation is already fine —
`PresenceStore.update` (`presence.py:30-33`) clears the previous conversation itself.

**Fix — delete the guard so the frame always sends:**

```ts
const setPresence = useCallback(
  (conversationId: string | null, state: 'viewing' | 'composing') => {
    lastPresence.current = { conversationId, state }
    send({ type: 'presence', conversationId, state })   // was: if (conversationId) send(...)
  },
  [send],
)
```

**No server change is needed — this was verified, not assumed.** `ws.py:66-72` reads
`cid = frame.get("conversationId")` and only runs the property check `if cid is not None`;
a `null` falls through to `presence.store.update(None, user, state)`, and `presence.py:38-39`
pops `_where[uid]` and returns the previous conversation in `changed`, which `ws.py:76`
broadcasts. The clear path already exists and has simply never been called.

Leave the reconnect replay at `ws.ts:149-151` guarded as it is — there is nothing to replay
for a null.

## 2. I8 — the presence spec cannot catch defect A (this is A's regression test)

`web/tests/e2e/presence.spec.ts:41` does `await marcus.goto('/app/board')` — a HARD
navigation, which tears down the WebSocket, so the clear comes from the server's
`finally: clear_user` (`server/app/realtime/ws.py:82-84`), not from the app's presence frame.
The assertion named "Leaving clears it" is green today while defect A is live. It is a direct
sibling of the `getByText('Delivered')` assertion that could not fail.

**Fix:** replace the `goto` with an in-app click that keeps the socket open —
`await marcus.getByRole('link', { name: 'Board' }).click()` — and tighten the assertion to
`toHaveCount(0, { timeout: 3000 })`. With A fixed the clear is immediate, so leaving the 20 s
window would mask a regression back to sweeper-dependence. Update the spec's comment at
:39-40, which currently describes the hard-navigation mechanism.

**Verify the ordering honestly:** this spec must FAIL against the unfixed `ws.ts` and PASS
after. Run it both ways and put both outputs in your report. If it passes before the fix,
the spec still is not testing what it claims — say so rather than proceeding.

## 3. Defect B — CRITICAL — SQLite silently ignores `skip_locked` (server)

`server/app/queue/jobs.py:29` uses `.with_for_update(skip_locked=True)`. Compiled against the
SQLite dialect on this project's SQLAlchemy 2.0.51 it yields `SELECT job.id FROM job` — no
lock clause, no warning, no error.

**The growth is EXPONENTIAL, not 2×.** `worker.py:41` calls `jobs.schedule_next_recurrence`,
a bare `enqueue` (`jobs.py:74-78`) with NO existence guard — unlike `ensure_recurring`
(`jobs.py:66-71`), which has one. Two processes claiming the same `sla.sweep` row both
complete it and both enqueue a successor: 1 → 2 → 4 → 8. Observed in the wild during Task 21:
826 MB DB, 2.7 M job rows, outbound SMS starved. `reclaim_stale` (`worker.py:27`, 60 s cutoff)
is a second entry point into the same race. The startup `ensure_recurring` loop
(`app/__init__.py:114-116`) is NOT the culprit — it is correctly guarded.

This is pre-existing (`jobs.py` last changed in `4555424`, outside this branch). Fix it anyway.

**Two changes. Do both; #1 alone prevents the explosion, #2 fixes the double-claim.**

1. Give `schedule_next_recurrence` the guard `ensure_recurring` already has:

```python
def schedule_next_recurrence(db: Session, job: Job) -> None:
    interval = RECURRING.get(job.type)
    if not interval:
        return
    if db.scalar(select(Job.id).where(Job.type == job.type,
                                      Job.status.in_([JobStatus.queued, JobStatus.running]))):
        return                      # another worker already scheduled the successor
    enqueue(db, job.type, job.payload,
            run_at=clock.now() + timedelta(seconds=interval), max_attempts=1)
```

2. Replace the no-op `with_for_update` with a compare-and-swap that works on both backends:

```python
def claim_due(db: Session, limit: int = 20) -> list[Job]:
    now = clock.now()
    ids = db.scalars(select(Job.id)
                     .where(Job.status == JobStatus.queued, Job.run_at <= now)
                     .order_by(Job.run_at).limit(limit)).all()
    claimed = [jid for jid in ids
               if db.execute(update(Job)
                             .where(Job.id == jid, Job.status == JobStatus.queued)
                             .values(status=JobStatus.running, locked_at=now)).rowcount]
    db.flush()
    return list(db.scalars(select(Job).where(Job.id.in_(claimed))).all()) if claimed else []
```

The `WHERE status = 'queued'` re-check under the write lock is what `skip_locked` was meant to
buy: a contended row is simply not claimed. Correct on PostgreSQL too.

**Required regression test:** call `claim_due` twice against the same rows with no intervening
commit and assert the second call returns nothing. Add a second test that
`schedule_next_recurrence` called twice for one job type leaves exactly one pending successor.
Match the existing style in `server/tests/`.

## 4. Defect C — E2E specs are type-checked by nothing

`web/tsconfig.json:20` includes `["src", "vitest.setup.ts"]`; `web/tsconfig.node.json:34`
includes `["vite.config.ts", "playwright.config.ts"]`. Neither reaches `tests/`, so
`npm run build` never type-checks the specs.

**Do NOT fix this by adding `"tests"` to `tsconfig.node.json`** — that project is
`composite: true, emitDeclarationOnly: true` with no `outDir`, so it would scatter `.d.ts`
files through `tests/e2e/`, and its `types: ["node"]` / no-DOM-lib setup is wrong for
Playwright specs.

**Fix — a third referenced project.** Create `web/tsconfig.e2e.json`:

```jsonc
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM"],
    "module": "ESNext", "moduleResolution": "bundler",
    "composite": true, "strict": true, "skipLibCheck": true,
    "emitDeclarationOnly": true, "outDir": "./.tsbuild/e2e",
    "types": ["node"]
  },
  "include": ["tests"]
}
```

Add `{ "path": "./tsconfig.e2e.json" }` to `references` in `web/tsconfig.json:21`, add
`.tsbuild/` to `web/.gitignore`, and add `"outDir": "./.tsbuild/node"` to
`tsconfig.node.json` at the same time — that also disposes of the stray
`web/vite.config.d.ts` / `web/playwright.config.d.ts` emitted into the working tree (M15).

Confirm `npx tsc -b` is clean afterwards and that no `.d.ts` appears under `tests/`.

## 5. I3 — `activePropertyId` survives logout (cross-user state bleed)

`SessionContext.tsx:6,43` writes `activePropertyId` to `localStorage`; `useLogout`
(`web/src/api/hooks/auth.ts:26-35`) clears the query cache but not `localStorage`. On a shared
front-desk machine — exactly the machine class plan ruling R1 names — user B signs in and
`SessionContext.tsx:52` resolves the stored id against B's memberships; if B also holds a
membership at A's property, B lands on A's property instead of B's own first membership.

Not a data leak (B only ever sees a property B can access), but it is cross-user state bleed.

**Fix:** `localStorage.removeItem('activePropertyId')` in `useLogout`'s `onSettled`, beside
`client.clear()`. Wrap in try/catch to match the existing accessor style. Add a test.

## 6. Ruling D52 — simulator phone chrome reverts to fixed iOS colours

`web/src/features/sim/PhoneFrame.tsx:14-23` currently themes the phone chrome with the app's
own tokens (`bg-surface`, `bg-surface2`, `border-border3`, `text-text`) while `:9-10` hardcodes
the two SMS bubble pairs. In dark mode that renders iOS-grey and iOS-green bubbles floating on
dark chrome — neither the mockup's phone nor a coherent dark theme, but a third thing that
reads as a rendering bug. `docs/mockups/Simulator.dc.html:60-87` paints the phone in fixed
iOS colours precisely because a real phone does not restyle itself when the staff app toggles.

**Fix:** add one `PHONE` palette constant at the top of `PhoneFrame.tsx` beside
`RECEIVED`/`SENT` — bezel `#000000`, body `#ffffff`, secondary `#8e8e93`, hairline `#d1d1d6`,
header `#f7f7f8` — and use it for the chrome. Carry the same style of comment that already
justifies the bubbles, so the next reviewer does not re-open this. **Keep the page AROUND the
frame fully tokenised**, exactly as the mockup does. `/sim` is dev-only and verified absent
from the production bundle, so this changes nothing users ship.

## 7. Defect D / ruling D51 — Departments admin screen (read-only)

`web/src/features/admin/AdminPage.tsx:20` greys FIVE labels as Phase 2. `docs/mockups/Admin.dc.html`
greys only THREE — Automations (:66), Blocked numbers (:67), Integrations (:68), each
explicitly `style="color: var(--text4)"` under the `:69` caption "Greyed items arrive in Phase 2".
Departments (:60) and Property settings (:64) are styled as LIVE items there.

**Fix:**
- **Departments becomes a live, READ-ONLY screen.** The server exposes only
  `GET /api/p/<property_id>/departments` (`server/app/api/departments.py:9-15`); spec §385
  lists only the GET. `useDepartments` already exists and is already consumed by four screens —
  reuse it, do not write a new hook. Build it with the existing `AdminTable` pattern and NO
  `EditPanel`, matching the mockup, which carries no create/edit affordance for Departments
  either. Add the route at `/app/admin/departments` and move the label from `PHASE_2` to `LIVE`,
  positioned after "Users & roles" as the mockup orders it (`Admin.dc.html:59-60`).
- **Property settings STAYS greyed.** No properties endpoint exists in Phase 1.
- **Keep the `:69` caption exactly as it is.** With Departments live it correctly describes the
  remaining four greyed items — which is what the mockup does.
- Add a test in the style of the existing admin tests.

## 8. The seven must-fix parked items

1. **`"2th stay"` ordinal — and it is in TWO files, not the one the ledger names.** Fix
   `GuestPanel.tsx:56` AND `ConversationHeader.tsx:154` (the same bug in caps,
   `${stay.stayCount}TH STAY`). Put one ordinal helper in `web/src/lib/` and use it in both.
   Cover 1st/2nd/3rd/4th and the 11th/12th/13th exceptions.
2. **`test_patch_prefs_merges_rather_than_replacing`** (Task 6) currently cannot distinguish
   merge from replace. Fix per the ledger's own prescription: seed an unrelated key directly,
   PATCH `theme`, assert the unrelated key survives.
3. **The hanging auth test** — add `{ timeout: 2000 }` to `RequireAuth.test.tsx:62`. One
   argument; it turns a pipeline stall into a legible failure.
4. **`LoginPage` already-authenticated redirect test** — the only untested branch of the login
   screen. Add it.
5. **`agents.error` is never checked** (`AnalyticsPage.tsx:149-152`): a failed agents fetch
   renders "No agent activity in this range", which is a false statement to a manager, not a
   missing datum. Render `agents.error.message` instead, matching how other screens render
   `ApiError`.
6. **`client.ts:19`'s doc comment is wrong** — it says the 401 hook is "installed by
   SessionProvider"; it is installed by `RequireAuth.tsx:19`. One line.
7. **`BoardPage`'s "All" tab resets the whole query string and drops `view=list`**
   (`BoardPage.tsx:78`). Delete only the filter params, not the whole string.

## 9. Two more small ones

- **M7 — a test that asserts nothing its title claims.** `ConversationView.test.tsx:95-101` is
  titled "warns but does not disable the thread" but only asserts that "opted out" text appears.
  Add `expect(screen.getByRole('textbox')).toBeEnabled()`. (`Composer.test.tsx:251-255` already
  does this correctly — match it.)
- **The permanently-broken lint script.** `web/package.json` ships
  `"lint": "eslint src --ext .ts,.tsx"` and there is no ESLint config, so it has never run.
  **Add a minimal working `.eslintrc.cjs`** — `@typescript-eslint` and `eslint-plugin-react-hooks`
  are already in devDependencies. Keep it minimal: recommended presets plus the react-hooks
  rules, nothing opinionated. `npm run lint` must exit 0 on the current tree; if it reports real
  problems, fix only what is trivially correct and report the rest rather than mass-editing.
  If a clean pass is not reachable cheaply, DELETE the script instead and say so — a permanently
  broken npm script in a repo someone else will clone is worse than an absent one.

---

## Out of scope — do not build these

I1 (note composer), I4 (closed work-order toggle), I5 (standalone work-order creation),
I6 (standalone work-order comment), I9 (guest panel previous-stays). These are the user's
call and are being put to them separately. Do not touch them. Do not delete `useAddNote` or
`useGuest` as "dead code" — they are the scaffolding those screens will use.

Also do not act on: M8 (analytics Custom range), M9, M10, M11, M12, M13 (inbox search — no
server support). They are being disclosed, not built.

## Verification before you commit

- `cd server && python -m pytest -q` — 256 passing plus your new job tests
- `cd web && npm test` — 358 passing plus your new tests
- `cd web && npx tsc -b` — clean, and no `.d.ts` under `tests/`
- `cd web && npm run lint` — exits 0 (or the script is gone)
- `cd web && npx playwright test` — both specs pass, and presence.spec.ts demonstrably fails
  against the unfixed `ws.ts` (capture both runs)
- `cd web && npm run build` — clean, and `/sim` still absent from `dist/`

Test output must be pristine — stray warnings are findings against you.

Commit in logical groups, not one giant commit. Suggested: (a) defect A + its spec, (b) defect B
+ tests, (c) defect C + tsconfig/outDir cleanup, (d) I3, (e) simulator chrome, (f) Departments
screen, (g) the parked items and small fixes.
