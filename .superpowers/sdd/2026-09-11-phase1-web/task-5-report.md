# Task 5 report: Session, capabilities, active property and route guarding

## What I implemented

Exactly the brief's file list, in TDD order:

- `web/src/auth/capabilities.ts` — `Capability` type, `CAPABILITIES` map (copied verbatim from
  `server/app/auth/permissions.py`, diffed line-by-line against it and confirmed identical),
  `hasCapability`, `landingPath`.
- `web/src/api/hooks/auth.ts` — `useSessionQuery`, `useLogin`, `useLogout`, verbatim from the brief.
- `web/src/test/harness.tsx` — `sessionFixture`, `testQueryClient`, `renderWithProviders`, verbatim
  from the brief.
- `web/src/auth/SessionContext.tsx` — `Session` type, `useSession`, `SessionProvider`, with the
  one correction called out below.
- `web/src/auth/RequireAuth.tsx` — the `<Outlet/>` guard, verbatim from the brief except the
  `Spinner` import path (see below).
- `web/src/auth/capabilities.test.ts`, `web/src/auth/SessionContext.test.tsx` — verbatim from the
  brief.

### Spinner import

The brief's `RequireAuth.tsx` snippet imports `Spinner` from `'../components/ui/Spinner'`. The
task instructions explicitly override this: `import { Spinner } from '../components/ui'`. I used
the index import as instructed.

## What I tested and the results

Full suite (`npm test`, i.e. `vitest run`): **10 files, 50 tests passed** — 7 capability tests + 1
landing-path test (counted as part of the 8 in `capabilities.test.ts`, actually 6 `it` blocks in
`hasCapability` + 1 in `landingPath` = 7 total, matching the file) and 6 `SessionContext` tests, on
top of the 37 from Tasks 1-4.

`npx tsc -b`: clean, no errors.

No `act()` warnings anywhere in the run. The only stderr output is React Router's own two "future
flag" deprecation warnings (`v7_startTransition`, `v7_relativeSplatPath`), which are React
Router's own console.warn calls triggered by `MemoryRouter` in the harness, not test failures, not
act() warnings, and not unhandled rejections. No unhandled promise rejections were reported by
Vitest at any point, including in the "throws outside provider" test, which suppresses
`console.error` for the expected React error-boundary log.

## TDD evidence

**RED — capabilities:**
```
cd web && npx vitest run src/auth/capabilities.test.ts
```
```
FAIL src/auth/capabilities.test.ts [ src/auth/capabilities.test.ts ]
Error: Failed to resolve import "./capabilities" from "src/auth/capabilities.test.ts". Does the file exist?
```
Expected: `capabilities.ts` did not exist yet.

**GREEN — capabilities:**
```
cd web && npx vitest run src/auth/capabilities.test.ts
```
```
✓ src/auth/capabilities.test.ts (7 tests) 2ms
Test Files  1 passed (1)
     Tests  7 passed (7)
```

**RED — session context:**
```
cd web && npx vitest run src/auth/SessionContext.test.tsx
```
```
FAIL src/auth/SessionContext.test.tsx [ src/auth/SessionContext.test.tsx ]
Error: Failed to resolve import "./SessionContext" from "src/auth/SessionContext.test.tsx". Does the file exist?
```
Expected: `SessionContext.tsx` did not exist yet.

**GREEN — session context (after also fixing the localStorage/vitest collision, see below):**
```
cd web && npx vitest run src/auth/SessionContext.test.tsx
```
```
✓ src/auth/SessionContext.test.tsx (6 tests) 78ms
Test Files  1 passed (1)
     Tests  6 passed (6)
```

**Full suite, GREEN:**
```
cd web && npm test
```
```
Test Files  10 passed (10)
     Tests  50 passed (50)
```

**TypeScript:**
```
cd web && npx tsc -b
```
(no output — clean)

## A real defect found and fixed: Node/vitest/jsdom localStorage collision

While writing `SessionContext.tsx`'s `SessionProvider` (real code, not just the test), I hit a
genuine environment bug, not a bad assertion in the brief. All 6 `SessionContext` tests failed with
`TypeError: Cannot read properties of undefined (reading 'clear')` on the very first line
(`localStorage.clear()`), plus a Node warning:
`ExperimentalWarning: localStorage is not available because --localstorage-file was not provided.`

Root cause (traced into `node_modules/vitest/dist/chunks/index.K90BXFOx.js`, `populateGlobal`):
Node 22+ ships its own global `localStorage` accessor (stable, no flag needed, in this environment's
Node v26.7.0), which throws/returns `undefined` unless `--localstorage-file` is passed. Vitest's
jsdom-environment setup only copies a jsdom `window` property onto the test `global` object when
that key is **not already present** on `global`. Since Node's own `localStorage` key already exists
on `global`, and `'localStorage'` isn't in vitest's hard-coded allowlist of keys it's willing to
override, jsdom's real, working `localStorage` implementation (verified working standalone via a
raw `new JSDOM()` probe) never gets installed — Node's broken stub wins. This is a real bug
reproducible with a minimal `typeof localStorage` probe test, independent of anything in the
brief's test code or my implementation.

Fix: `web/vite.config.ts` — added `test.poolOptions.{threads,forks}.execArgv:
['--no-experimental-webstorage']` (vitest's default pool is `forks`; I set it on both so the fix
survives a future pool change). This removes Node's global entirely, so vitest's `k in global`
check is false and jsdom's real localStorage gets copied onto `global` as intended. I confirmed
with a `node --no-experimental-webstorage -e "console.log('localStorage' in globalThis)"` probe
that this is exactly what flips the check, and re-ran the full suite via plain `npm test` (not a
one-off env var) to confirm the fix holds through the normal script and through vitest's actual
worker pool, not just a single in-process run.

This is scoped as a separate commit (`30ce459`, "fix(web): disable Node's native webstorage global
so vitest's jsdom localStorage works") since it's test infrastructure, not part of the brief's file
list, and orthogonal to the feature commit.

## The `logoutMutation` → stable `mutate` change

Per the task instructions' correction, I destructured `useLogout()` to `const { mutate: logout } =
useLogout()` instead of holding the whole mutation object, and used `logout` (not
`logoutMutation.mutate()`) both inside the `useMemo` closure and in its dependency array. Everything
else about the memo is unchanged from the brief.

What I noticed: this is a real, not theoretical, problem. `useMutation` returns a fresh object every
render in TanStack Query v5 (only its methods, including `mutate`, are stable across renders), so
`logoutMutation` in the dependency array would have made the `useMemo` recompute — and thus every
`useSession()` consumer re-render — on literally every render of `SessionProvider`, including ones
triggered by totally unrelated state elsewhere in the tree re-rendering `SessionProvider` for no
reason. Depending on the destructured `mutate` fixes this: the memo now only recomputes when
`data`, `stored`, or the (also-stable, `useCallback`'d) `setPropertyId` actually change.

## Files changed

- `web/src/auth/capabilities.ts` (new)
- `web/src/auth/capabilities.test.ts` (new)
- `web/src/api/hooks/auth.ts` (new)
- `web/src/test/harness.tsx` (new)
- `web/src/auth/SessionContext.tsx` (new)
- `web/src/auth/SessionContext.test.tsx` (new)
- `web/src/auth/RequireAuth.tsx` (new)
- `web/vite.config.ts` (modified — `poolOptions.threads/forks.execArgv` fix, see above)

## Self-review

- **Completeness:** all 7 capability-test cases (6 in `hasCapability`, 1 in `landingPath`, matching
  the brief's file exactly) pass. `RequireAuth` handles pending (`Spinner`), error/no-data
  (`Navigate` to `/login` with `state.from`), no-memberships (inline message), and authenticated
  (`SessionProvider` + `Outlet`) as four visibly distinct branches.
- **Quality:** the active-property fallback (`data.memberships.find(...) ?? data.memberships[0]!`)
  correctly falls back to the first membership when the stored id doesn't match any membership —
  covered by the "ignores a stored property the user no longer has access to" test. Role comes from
  the resolved `membership` object (the active one), not `data.memberships[0]` directly — covered by
  the "takes the role from the active property, not the first one" test. Both `localStorage` reads
  (initial `useState` initializer) and writes (`setPropertyId`) are wrapped in try/catch.
- **Discipline:** I did not add anything beyond the brief's interfaces — no extra context fields,
  no extra exports. `UserOut`'s fixture in `harness.tsx` does not include `notificationPrefs`, per
  the instruction that a later task adds it.
- **Testing:** the tests exercise real behavior (localStorage read/write, membership resolution,
  the thrown error outside a provider) rather than mocking around it. Output is pristine — no
  act() warnings, no unhandled rejections. The only non-test-result stderr is React Router's own
  future-flag deprecation notices, unrelated to test correctness.

## Issues or concerns

- The `web/vite.config.ts` change is outside Task 5's stated file list, but was necessary to make
  Step 9 (`npm test` passing) achievable at all on this machine's Node version (v26.7.0). It's a
  test-infrastructure-only change (no application logic touched to work around it), kept in its own
  commit, and documented above per the "report the defect, don't bend the code" instruction. Worth
  the review agent double-checking this reasoning, since it's a judgment call about scope.
- React Router's two future-flag console warnings will appear in every test that renders
  `MemoryRouter` (i.e. via `renderWithProviders`) for as long as v6 is in place. They are pre-existing
  library behavior, not something Task 5 introduced or should silence, but future task authors should
  not mistake them for `act()` warnings when reading the harness's test output — reporting this now in
  case the human reader wants to note it in the vitest config's known-noise list rather than have it
  keep surprising `test.only` debugging sessions across all 15 later tasks.

---

## Fix round 1 (review finding: unguarded `execArgv` flag)

**Finding:** the previous fix hard-coded `execArgv: ['--no-experimental-webstorage']`. Node
rejects unrecognised flags by exiting immediately (`bad option`), and that flag doesn't exist
before Node 22.4. This project's floor is Node 20 (no `engines` field existed to say so), so
anyone on Node 20 following the plan's own setup instructions would get every test worker
crashing at process start — a total suite outage with a cryptic error, strictly worse than the
`localStorage` bug being worked around.

The reviewer also flagged, correctly, that probing the *symptom* (`typeof
globalThis.localStorage !== 'undefined'`) doesn't work: on Node 26.7.0 the accessor exists and
still shadows jsdom, but reads back as `undefined` (with an `ExperimentalWarning`), so a
symptom-probe would evaluate `false`, skip the flag, and silently leave the bug in place.

### What I changed

`web/vite.config.ts`:
- Added `nodeAcceptsFlag(flag)` — spawns `process.execPath` with `[flag, '-e', '']` and
  `stdio: 'ignore'`, returning `status === 0`. Any spawn failure is caught and treated as
  "unsupported," never thrown, and nothing is printed in either branch.
- Researched (via web search, then confirmed by fetching the actual GitHub PRs) that the
  disabling flag was **renamed partway through Node 25**: `--no-experimental-webstorage` was
  the only spelling from Node 22.4 (when Web Storage was introduced, opt-in) through Node 24.x;
  PR nodejs/node#57666 unflagged it by default in Node 25.0.0 and introduced `--no-webstorage`
  as the new negated name; PR nodejs/node#60708 (merged into 25.2.1) revisited the "experimental"
  labelling but didn't document whether the old spelling keeps working as an alias on every
  point release in between. Rather than gamble on exactly which Node 25.x point release added
  the alias back, I probe **both** spellings and use whichever this Node build accepts:
  `['--no-webstorage', '--no-experimental-webstorage'].find(nodeAcceptsFlag)`. This closes the
  version-window risk without needing to pin down the exact alias history.
- `webStorageExecArgv` is `[]` when neither flag is accepted (Node 20–22.3, or hypothetically a
  future Node that renames it again) — `poolOptions.threads/forks.execArgv` then receives an
  empty array, i.e. no flag, which is exactly correct there (see version-window answer below).

`web/package.json`:
- Added `"engines": { "node": ">=20" }`, matching the plan's stated floor and this repo's
  `@types/node": "^20.16.5"`.

**`.nvmrc`: not added.** My reasoning: `.nvmrc` pins contributors to one specific version via
auto-switching tools (nvm/fnm/volta), which is a stronger, more opinionated statement than "this
is the minimum supported version." This dev machine itself runs Node 26, two majors past the
floor, and the whole point of this fix is that the suite now works correctly across that entire
range via the probe rather than requiring everyone to downgrade to match a pinned file. Adding
`.nvmrc: 20` would actively fight that by prompting auto-switching tools to downgrade newer
machines for no correctness benefit. If the team later wants CI to pin an exact version for
reproducibility (a different, legitimate reason than "avoid this bug"), that's a call for
whoever sets up CI, with knowledge of what CI actually runs — not something to bake in here on
my own judgment.

### Probe discriminates: evidence

```
$ node /tmp/probe-demo/probe.mjs
node --version: v26.7.0
accepts --no-webstorage: true
accepts --no-experimental-webstorage: true
accepts --no-such-flag-exists (bogus): false
```
(script is the same `nodeAcceptsFlag` body as in `vite.config.ts`, run standalone)

Cross-checked directly against `node` itself (not just the wrapped function), to rule out a bug
in the probe logic:

```
$ node --no-webstorage -e "console.log('localStorage' in globalThis)"
false
$ node --no-experimental-webstorage -e "console.log('localStorage' in globalThis)"
false
$ node --no-such-flag-exists -e "console.log(1)"
C:\Program Files\nodejs\node.exe: bad option: --no-such-flag-exists
$ echo $?
9
```

Both real spellings are accepted (exit 0) and actually remove the global (`'localStorage' in
globalThis` → `false`, vs. `true` with no flag). The bogus flag is rejected by Node itself with
exit code 9 and a "bad option" message — confirming the probe isn't a trivial always-true
function; it reflects Node's real CLI parsing.

### The version-window question

Reasoning through each range:

- **Node < 22.4:** no native Web Storage global exists at all (feature didn't exist yet), so
  jsdom's `localStorage` is never shadowed. No flag needed; the probe finds neither spelling
  accepted, `webStorageExecArgv` is `[]`, tests pass. **Confirmed by the flag's own absence being
  exactly what "no such option" reports.**
- **Node 22.4 – 24.x:** the feature exists but is **off by default** (opt-in via
  `--experimental-webstorage`, per the Node 22.4.0 release notes). Nobody in this project passes
  that flag, so the global is never installed by default and jsdom is never shadowed here either.
  No flag needed; same as above. (If someone *did* pass `--experimental-webstorage` themselves in
  this range, they'd need `--no-experimental-webstorage` to undo it — the probe finds that
  spelling, since it's the only one that exists in this range.)
- **Node 25.0.0+:** the feature is **on by default** (nodejs/node#57666, "unflag
  --experimental-webstorage by default", landed in 25.0.0), so jsdom is shadowed unless disabled.
  The renamed flag `--no-webstorage` exists starting at 25.0.0 by the same PR. This machine's
  Node 26.7.0 accepts both spellings.
- **The one gap I cannot fully close from documentation alone:** whether `--no-experimental-webstorage`
  specifically (the *old* name) kept working as an alias on every single point release from
  25.0.0 onward, or only from some later point release (e.g. 25.2.1, where PR #60708 touched the
  experimental-status labelling). I could not find a source that pins this down precisely, and I
  don't have another Node 25.0.0-exact binary on this machine to test directly — **so I'm stating
  this as an honest unknown rather than asserting it.** It does not leave a real gap in practice,
  though: the probe tries `--no-webstorage` **first**, and that is the name the same PR that
  turned the feature on by default (25.0.0) also introduced. So even in the narrowest possible
  window — a hypothetical Node 25.0.0 where only the new name works — the probe still finds
  `--no-webstorage` and applies it correctly. The only way this fix could fail is a Node version
  that has the global on by default *and* accepts neither spelling, and I found no evidence such
  a version exists.

### Tests run

`npx vitest run src/auth` (the suite that exercises `localStorage`):
```
✓ src/auth/capabilities.test.ts (7 tests)
✓ src/auth/SessionContext.test.tsx (6 tests)
Test Files  2 passed (2)
     Tests  13 passed (13)
```

Full suite, `npm test`:
```
Test Files  10 passed (10)
     Tests  52 passed (52)
```
(52 vs. the 50 reported before this fix round is `Dialog.test.tsx` — pre-existing, untouched by
either of my commits; confirmed by re-running that file alone, consistently 7 tests both times.)

`npx tsc -b`: clean, no output.

No noise was printed by the probe during any of these runs — verified by reading the full
`npm test` output above line by line; the only stderr lines are the two pre-existing React
Router future-flag warnings already called out above.

### Files changed (this round)

- `web/vite.config.ts` (modified — guarded, dual-spelling probe replaces the hard-coded flag)
- `web/package.json` (modified — added `engines.node`)
