# Task 7: Theme — dark default, light toggle, persisted per user

## What I implemented

### Part 1 — theme provider (the brief)

- `web/src/api/hooks/auth.ts`: added `useSetPrefs()` — a `useMutation<SessionOut, ApiError, { theme: 'dark' | 'light' | 'system' }>` that `PATCH`es `/api/auth/prefs` and, on success, writes the returned session back into the query cache via `client.setQueryData(qk.session, session)`. Implemented verbatim from the brief.
- `web/src/theme/ThemeContext.tsx` (new): `ThemeProvider` + `useTheme()`, implemented verbatim from the brief.
  - `storedChoice()` reads `notificationPrefs.theme`, validates it against the three-member `CHOICES` array, and falls back to `'system'` for anything else (missing, wrong type, or an unrecognized string like `'sepia'`).
  - `devicePrefersDark()` accesses `window.matchMedia` with optional chaining and defaults to `true` (dark) when it's undefined — defensive per the task's instructions.
  - `resolved` is computed synchronously from `theme` + device preference; an effect writes it to `document.documentElement.dataset.theme`.
  - `setTheme()` updates local component state first (instant, optimistic) and fires the mutation in the background; a failed mutation never touches `theme` state, so the chosen value stays on screen for the session.
- `web/src/test/harness.tsx`: added `prefs?: Record<string, unknown>` to `sessionFixture`'s options type and `notificationPrefs: opts.prefs ?? {}` to the fixture's `user` object, per the brief.
- `web/src/theme/ThemeContext.test.tsx` (new): the brief's 7-test file, with two fixes (see Defects Found below).

### Part 2 — silence React Router future-flag warnings

- `web/src/test/harness.tsx`: `renderWithProviders`'s `MemoryRouter` now passes `future={{ v7_startTransition: true, v7_relativeSplatPath: true }}`.

## Defects found in the brief (fixed, not worked around)

1. **Unused import in the literal test.** The brief's `ThemeContext.test.tsx` imports `qk` from `'../api/queryKeys'` but never references it. This project has `noUnusedLocals: true` in `tsconfig.json`, so the literal test would fail `tsc -b`. Fix: removed the unused import. No behavioral change to the test.

2. **Missing `SessionProvider` in the literal test's render tree.** `ThemeContext.tsx` calls `useSession()` from `../auth/SessionContext` (Task 5), which throws `"useSession must be used inside a SessionProvider"` unless a `<SessionProvider>` ancestor is present. The brief's `withTheme()` helper renders `<ThemeProvider>` directly with no `<SessionProvider>` wrapper, so all 7 tests failed with that error on first run. Every other test in the codebase that touches `useSession` (e.g. `SessionContext.test.tsx`) wraps explicitly in `<SessionProvider>`, and in the real app `RequireAuth` composes `<SessionProvider><Outlet /></SessionProvider>` — `ThemeProvider` will always sit inside that subtree in production. Fix: wrapped `withTheme()`'s tree in `<SessionProvider>`, matching the established pattern:
   ```tsx
   function withTheme(session = sessionFixture()) {
     return renderWithProviders(
       <SessionProvider>
         <ThemeProvider>
           <Probe />
         </ThemeProvider>
       </SessionProvider>,
       { session },
     )
   }
   ```
   This is a one-line addition to the test scaffolding; no assertions or provider/hook logic were changed.

Nothing in `useSetPrefs` or `ThemeContext.tsx`'s logic needed to change — both are exactly as specified in the brief.

## TDD evidence

**RED** — `cd web && npx vitest run src/theme` (before `ThemeContext.tsx` existed):
```
FAIL  src/theme/ThemeContext.test.tsx [ src/theme/ThemeContext.test.tsx ]
Error: Failed to resolve import "./ThemeContext" from "src/theme/ThemeContext.test.tsx". Does the file exist?
 Test Files  1 failed (1)
      Tests  no tests
```
Expected failure: the brief's step 2 says "FAIL — cannot resolve `./ThemeContext`," confirmed exactly.

After creating `ThemeContext.tsx`/`useSetPrefs` (before fixing defect #2), the same command failed differently — all 7 tests ran and failed with `useSession must be used inside a SessionProvider`, which is defect #2 above, not a defect in the provider itself.

**GREEN** — `cd web && npx vitest run src/theme` (after both defect fixes):
```
✓ src/theme/ThemeContext.test.tsx (7 tests) 241ms

 Test Files  1 passed (1)
      Tests  7 passed (7)
```
All 7 brief tests pass.

## Part 2 evidence

**Before** (full theme suite run, `SessionProvider` fix in place, future flags not yet added):
```
stderr | src/theme/ThemeContext.test.tsx > ThemeProvider > defaults to system when the user has no stored preference
⚠️ React Router Future Flag Warning: React Router will begin wrapping state updates in `React.startTransition` in v7. You can use the `v7_startTransition` future flag to opt-in early. For more information, see https://reactrouter.com/v6/upgrading/future#v7_starttransition.
⚠️ React Router Future Flag Warning: Relative route resolution within Splat routes is changing in v7. You can use the `v7_relativeSplatPath` future flag to opt-in early. For more information, see https://reactrouter.com/v6/upgrading/future#v7_relativesplatpath.

 ✓ src/theme/ThemeContext.test.tsx (7 tests) 261ms
```

**After** (added `future={{ v7_startTransition: true, v7_relativeSplatPath: true }}` to `MemoryRouter` in `harness.tsx`):
```
✓ src/theme/ThemeContext.test.tsx (7 tests) 241ms

 Test Files  1 passed (1)
      Tests  7 passed (7)
```
Warnings gone, same 7 tests still pass. Opting in did not change behaviour or break any existing test.

## Full verification

`cd web && npm test` (full suite, after both parts):
```
✓ src/index.css.test.ts (4 tests)
✓ src/api/types.generated.test.ts (2 tests)
✓ src/api/client.test.ts (10 tests)
✓ src/auth/capabilities.test.ts (7 tests)
✓ src/lib/cn.test.ts (3 tests)
✓ src/components/ui/Avatar.test.tsx (4 tests)
✓ src/auth/SessionContext.test.tsx (6 tests)
✓ src/components/ui/Button.test.tsx (4 tests)
✓ src/theme/ThemeContext.test.tsx (7 tests)
✓ src/components/ui/Dialog.test.tsx (7 tests)
✓ src/components/ui/Dropdown.test.tsx (5 tests)

 Test Files  11 passed (11)
      Tests  59 passed (59)
```
No `act()` warnings, no unhandled rejections, no React Router future-flag warnings anywhere in the output (including the "keeps the chosen theme on screen even if the save fails" test, whose rejected `fetch` mock is swallowed into React Query's mutation error state as documented in the brief).

`cd web && npx tsc -b`: no output — clean.

## Files changed

- `web/src/api/hooks/auth.ts` — added `useSetPrefs`
- `web/src/theme/ThemeContext.tsx` — new: `ThemeProvider`, `useTheme`
- `web/src/theme/ThemeContext.test.tsx` — new: 7 tests (brief's literal tests, plus the two scaffolding fixes above)
- `web/src/test/harness.tsx` — `sessionFixture` gains `prefs` option / `notificationPrefs` field (Part 1); `MemoryRouter` gains `future` flags (Part 2)

## Self-review

- **Completeness:** all 7 brief tests pass; the resolved theme reaches `document.documentElement.dataset.theme` (verified directly in 5 of the 7 tests).
- **Quality:** `matchMedia` access is optional-chained (`window.matchMedia?.(...)`) and defaults to dark when absent. An invalid stored value (`'sepia'`) falls back to `'system'` rather than propagating. A failed save (`fetch` rejecting) leaves `theme`/`resolved` at the user's chosen value — confirmed by the "keeps the chosen theme on screen even if the save fails" test.
- **Discipline:** implementation matches the brief exactly; no extra theme values, no `localStorage` fallback for theme, no unrelated refactoring. The only deviations from the brief's literal text are the two defect fixes above (both additive, not logic changes) plus Part 2's harness change, which was explicitly scoped into this task.
- **Testing:** tests exercise real DOM state (`dataset.theme`), real `fetch` mock call shape (URL, method, body), and real mutation failure — not mocked implementation internals. Output is pristine: no `act()` warnings, no unhandled rejections, no router warnings.

## Issues / concerns

- Two real defects were found in the brief's literal `ThemeContext.test.tsx` (unused `qk` import; missing `SessionProvider` wrapper) — both are documented above, both were fixed rather than worked around, and neither required touching the approved provider/hook logic.
- `npx eslint` currently fails project-wide with "ESLint couldn't find a configuration file" — this is a pre-existing repo state, not something introduced by this task, and out of scope for it.
