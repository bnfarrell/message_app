# Final fix wave — report

Branch `main`. Base `336d9ad`. Head after this wave: `e6fbfb8`. Working tree clean.

All nine sections done. Nothing on the out-of-scope list was touched: `useAddNote` and
`useGuest` are untouched, and no work was done on I1, I4, I5, I6, I9, M8, M9, M10, M11, M12
or M13.

## Commits

| SHA | Subject |
| --- | --- |
| `0f53d2c` | fix(web): send the presence clear frame when leaving the inbox |
| `cb4c2ff` | fix(server): stop recurring jobs multiplying when two workers race |
| `9a0564d` | build(web): type-check the e2e specs and stop emitting .d.ts into the tree |
| `6be8006` | fix(web): drop the stored active property on sign-out |
| `ef64265` | fix(web): give the simulator phone fixed iOS chrome, per ruling D52 |
| `12dec16` | feat(web): read-only Departments admin screen, per ruling D51 |
| `46ff413` | fix: the seven parked must-fix items, plus M7 |
| `e6fbfb8` | build(web): add the missing ESLint config so npm run lint works |

---

## 1. Defect A — presence sticks forever on in-app navigation

`web/src/api/ws.ts` — deleted the `if (conversationId)` guard so the clear frame reaches the
wire, with a comment saying why a null id is not a no-op. No server change; the diagnosis in
the brief (`ws.py:66-72` → `presence.py:38-39` already handles a null) was read and holds.
The reconnect replay at `ws.ts:149-151` was left guarded as instructed.

## 2. I8 — the presence spec could not catch defect A

`web/tests/e2e/presence.spec.ts` — the hard `marcus.goto('/app/board')` became
`marcus.getByRole('link', { name: 'Board' }).click()`, the 20 s window became 3 s, and the
comment at the top of the step was rewritten to describe the in-app mechanism and to say
explicitly why a `goto` would stay green.

**Ordering proved honestly. Before the `ws.ts` fix, with the new spec:**

```
Running 1 test using 1 worker
  x  1 tests\e2e\presence.spec.ts:13:1 > two agents on one conversation each see the other within 2 seconds (4.7s)

  1) tests\e2e\presence.spec.ts:13:1 > two agents on one conversation each see the other within 2 seconds

    Error: expect(locator).toHaveCount(expected) failed
    Locator:  getByText(/Marcus is/)
    Expected: 0
    Received: 1
    Timeout:  3000ms
      - waiting for getByText(/Marcus is/)
        10 x locator resolved to 1 element
           - unexpected value "1"
      > 44 |   await expect(ava.getByText(/Marcus is/)).toHaveCount(0, { timeout: 3000 })
  1 failed
```

**After the fix:**

```
Running 2 tests using 1 worker
  ok  1 tests\e2e\presence.spec.ts:13:1 > two agents on one conversation each see the other within 2 seconds (1.6s)
  ok  2 tests\e2e\smoke.spec.ts:18:1 > a guest text becomes a reply, a work order, and a closed loop (7.5s)
  2 passed (9.8s)
```

So the spec now fails for the reason it names and passes only once the app actually sends the
frame.

## 3. Defect B — CRITICAL — SQLite silently ignores `skip_locked`

Diagnosis re-verified before acting, against the installed SQLAlchemy (**2.0.52**, not the
2.0.51 the brief names — immaterial):

```
SELECT job.id
FROM job
WHERE job.status = ?
 LIMIT ? OFFSET ?
```

No `FOR UPDATE`, no `SKIP LOCKED`, no warning. Both prescribed changes applied to
`server/app/queue/jobs.py`:

1. `schedule_next_recurrence` now carries the same queued/running existence guard
   `ensure_recurring` has.
2. `claim_due` is a compare-and-swap: `SELECT id`, then a per-row
   `UPDATE … WHERE id = ? AND status = 'queued'`, keeping only the ids whose `rowcount` is
   non-zero.

Single-worker behaviour is unchanged — an uncontended row always matches its own predicate, so
it is always claimed. The full server suite (which exercises the worker end to end: retries,
backoff, dead-lettering, stale reclaim, recurrence, SLA sweeps, snooze wake) is green.

### The prescribed regression test could not fail — this is a finding

The brief asked for "call `claim_due` twice against the same rows with no intervening commit
and assert the second call returns nothing". That test passes against the **unfixed** code
too: the old implementation set `status = running` on the ORM objects and flushed, so the
second call's `WHERE status = 'queued'` filtered the rows out inside the same transaction.
It would have been a second assertion that cannot fail — the same class of defect as I8.

What I wrote instead, in `server/tests/test_queue.py`:

- `test_claim_due_does_not_take_a_row_another_worker_claimed_mid_select` — a SQLAlchemy
  `after_execute` listener fires in the window **between** `claim_due`'s SELECT and its
  UPDATE and claims the row from a separate, committed session. That is exactly where the
  real race lives, and it is deterministic: no threads, no sleeps, no timing. The test also
  asserts the contending claim actually ran, so it cannot pass vacuously.
  (This works because pysqlite does not open a transaction for a SELECT, so the steal can
  commit without deadlocking the session under test.)
- `test_schedule_next_recurrence_leaves_exactly_one_successor` — two calls for one job type
  leave exactly one queued successor, at the right `run_at`.

Both were run against the unfixed code first and both failed:

```
FAILED tests/test_queue.py::test_claim_due_does_not_take_a_row_another_worker_claimed_mid_select
FAILED tests/test_queue.py::test_schedule_next_recurrence_leaves_exactly_one_successor
2 failed, 7 deselected in 0.69s
```

`test_schedule_next_recurrence_leaves_exactly_one_successor` failed with `assert 2 == 1` —
the doubling itself, reproduced.

## 4. Defect C — E2E specs were type-checked by nothing

Added `web/tsconfig.e2e.json` exactly as specified, referenced it from `web/tsconfig.json`,
added `.tsbuild/` to `web/.gitignore`, and gave `tsconfig.node.json` an `outDir`. Deleted the
two stray `vite.config.d.ts` / `playwright.config.d.ts` from the web root (M15) and the two
orphaned `*.tsbuildinfo` files; all four are now written under `.tsbuild/`.

Proved the new project actually checks the specs by appending
`const oops: number = 'nope'` to `smoke.spec.ts` and running `npx tsc -b`:

```
tests/e2e/smoke.spec.ts(102,7): error TS2322: Type 'string' is not assignable to type 'number'.
```

Reverted; `npx tsc -b` clean, and `find tests -name "*.d.ts"` returns nothing.

## 5. I3 — `activePropertyId` survived logout

`web/src/api/hooks/auth.ts` — `localStorage.removeItem('activePropertyId')` in `useLogout`'s
`onSettled` beside `client.clear()`, in a try/catch matching the accessor style in
`SessionContext.tsx`.

Test added in `web/src/auth/SessionContext.test.tsx` ("clears the stored active property on
sign-out so it cannot follow the next user"). Verified it fails when the `removeItem` line is
stubbed out (1 failed / 6 passed), and passes with it.

## 6. Ruling D52 — simulator phone chrome

`web/src/features/sim/PhoneFrame.tsx` — added a `PHONE` constant beside `RECEIVED`/`SENT` and
used it for the chrome: bezel `#000000`, body `#ffffff`, header `#f7f7f8`, hairline
`#d1d1d6`, secondary `#8e8e93`. The substitution is colour-for-colour against the tokens that
were there (`border-border3` → bezel, `bg-surface` → body, `bg-surface2` → header,
`border-border` → hairline, `text-text3` → secondary, `bg-accent`/`text-accentText` on the
"HV" badge → secondary/body, matching the grey circle in `Simulator.dc.html:63`); no layout
changed. The comment that already justified the bubbles was extended to cover the chrome and
to name the mockup. The page around the frame is untouched and still fully tokenised.

One deviation to flag: I added a sixth key, `text: '#111111'`, because the body text had to
stop following `text-text` and the five named colours contain no foreground. It is the same
value `RECEIVED.color` already uses and the same one the mockup uses.

## 7. Defect D / ruling D51 — Departments admin screen

- New `web/src/features/admin/DepartmentsAdmin.tsx`: read-only, reuses the existing
  `useDepartments` hook, built on `AdminTable`, no `EditPanel`, no create button. Columns are
  Name / Type / Escalation / Active. Selection highlights a row and does nothing else.
- `AdminPage.tsx`: `Departments` moved from `PHASE_2` to `LIVE`, positioned directly after
  "Users & roles" as `Admin.dc.html:59-60` orders it; route added at `/app/admin/departments`.
- `Property settings` stays in `PHASE_2`. The `:69` caption is unchanged and now describes
  the remaining four greyed items.
- `AdminPage.test.tsx`: the two existing tests were updated (they asserted Departments was
  greyed), the live-sections test now also pins the mockup's ordering, and a new test asserts
  the rows render and that there is no create/save affordance.

## 8. The seven must-fix parked items

1. **`"2th stay"`** — new `web/src/lib/ordinal.ts` plus `ordinal.test.ts` (4 tests covering
   1st/2nd/3rd/4th, the 11/12/13 exception, the return to st/nd/rd at 21–23 and 101, and 0).
   Used in `GuestPanel.tsx:57` and in `ConversationHeader.tsx:44` (`.toUpperCase()` for the
   caps variant). Both call sites confirmed by grep; no third exists.
2. **`test_patch_prefs_merges_rather_than_replacing`** — seeds `{"digestHour": 7}` directly on
   the user row, PATCHes `theme`, asserts both the new theme and the survival of the unrelated
   key. Verified it fails (`KeyError: 'digestHour'`) when the endpoint is made to replace
   rather than merge.
3. **Hanging auth test** — `RequireAuth.test.tsx` redirect assertion now bounded at 2000 ms.
4. **`LoginPage` already-authenticated redirect** — new test: a manager session in the cache
   lands on the Analytics route and the email field is gone.
5. **`agents.error`** — `AnalyticsPage.tsx` now renders an `EmptyState` with
   `agents.error.message` ahead of the empty-list branch, matching how the overview error is
   rendered on the same screen.
6. **`client.ts` doc comment** — "installed by SessionProvider" → "installed by RequireAuth".
7. **Board "All" tab** — `BoardPage.tsx` gained a `clearFilters()` that deletes only `mine`,
   `dept` and `urgent`. Test added; verified it fails against the old
   `new URLSearchParams()` behaviour.

## 9. Two more small ones

- **M7** — `ConversationView.test.tsx` now asserts
  `expect(screen.getByRole('textbox')).toBeEnabled()`, matching `Composer.test.tsx:251-255`.
- **Lint** — added `web/.eslintrc.cjs`: `eslint:recommended` +
  `plugin:@typescript-eslint/recommended` + the two react-hooks rules, nothing else. **No
  source change was needed**: `npm run lint` exits 0 on the current tree. Confirmed the config
  is really working rather than vacuously matching nothing — a probe file with `any` and
  `debugger` produced two errors and exit 1, and `eslint -f json` reports **123 files linted**.
  The fallback (deleting the script) was not needed.

---

## Verification

| Command | Result |
| --- | --- |
| `cd server && python -m pytest -q` | `258 passed in 29.75s` (256 baseline + 2 new job tests) |
| `cd web && npm test` | `44 passed (44)` files, `366 passed (366)` tests (358 baseline + 8 new) |
| `cd web && npx tsc -b` | exit 0; `find tests -name "*.d.ts"` empty |
| `cd web && npm run lint` | exit 0, no output |
| `cd web && npx playwright test` | `2 passed (15.6s)` |
| `cd web && npm run build` | `148 modules transformed`, `built in 2.51s`, no warnings |

`/sim` still absent from the production bundle: `grep -ril "PhoneFrame\|sms-in\|Simulator" dist/`
and `grep -rl "8e8e93" dist/` both return nothing.

No warnings in any run.

New test count: 2 server (`test_queue.py`), 8 web (4 × `ordinal`, 1 × SessionContext logout,
1 × AdminPage departments, 1 × BoardPage All-tab, 1 × LoginPage redirect). One server test
(`test_patch_prefs_merges_rather_than_replacing`) rewritten rather than added.

---

## Found but not fixed

1. **The brief's prescribed `claim_due` regression test cannot fail.** Detailed under §3
   above. I wrote a test that can, and said so rather than shipping the vacuous one.
2. **`useLogout` duplicates the `'activePropertyId'` string literal** that `SessionContext.tsx`
   holds privately as `STORAGE_KEY`. Exporting and importing it would make
   `SessionContext → hooks/auth → SessionContext` circular, so the literal is duplicated on
   purpose. If it ever changes, both sites must change. Not fixed — a shared constants module
   is a refactor, not a correction.
3. **`web/.gitignore` still carries `/*.config.d.ts`**, which is now dead: with `outDir` set on
   the node project nothing is emitted to the web root any more. Left in place as unrelated
   tidying.
4. **`AdminTable` rows are `tabIndex={0}` and `cursor-pointer` unconditionally**, so on a
   read-only screen they are focusable and look clickable for a selection that does nothing
   but highlight. Following the brief's "use the existing `AdminTable` pattern" instruction
   rather than adding a read-only mode to a component four other screens depend on. Worth a
   look if more read-only admin screens arrive.
5. The brief cites SQLAlchemy 2.0.51; the installed version is 2.0.52. The `skip_locked`
   no-op was re-verified against the installed version, so this changes nothing.

## Not completed

Nothing. All nine sections are done.
