# Task 10 report: SMS segments, time formatting and the SLA chip

## What I implemented

- `web/src/lib/segments.ts` — `isGsm7`, `segmentCount`, `charCount`. Transcribed
  `GSM7_BASIC` / `GSM7_EXTENDED` character-by-character from `server/app/domain/sms.py`
  (including the `\n`, `\r`, `\f` control characters) and mirrored `is_gsm7`,
  `_gsm7_septets` → `gsm7Septets`, `_utf16_units` → `utf16Units` (as `body.length`, since
  JS strings are already UTF-16), and `segment_count` → `segmentCount`.
- `web/src/lib/time.ts` — `formatCountdown`, `relativeTime`, `formatClock`,
  `formatDuration`. Hand-rolled, no date library, exactly as the brief's Step 4 code.
- `web/src/components/SlaChip.tsx` — exports `slaState` (pure) and `SlaChip` (component),
  exactly as the brief's Step 7 code, unmodified.
- Three test files (`segments.test.ts`, `time.test.ts`, `SlaChip.test.tsx`) copied verbatim
  from the brief's Steps 1 and 5, with one exception noted below (defect found in the given
  `SlaChip.test.tsx`, fixed without touching any assertion or value).

## What I tested and the results

`npm test` (full suite): **17 files / 123 tests, all passing**, pristine output — no
`act()` warnings, no unhandled rejections. `npx tsc -b`: clean, no output.

## TDD evidence

**RED** — `cd web && npx vitest run src/lib/segments.test.ts src/lib/time.test.ts src/components/SlaChip.test.tsx` (test files written, source files not yet created):

```
FAIL src/components/SlaChip.test.tsx [ src/components/SlaChip.test.tsx ]
Error: Failed to resolve import "./SlaChip" from "src/components/SlaChip.test.tsx". Does the file exist?
FAIL src/lib/segments.test.ts [ src/lib/segments.test.ts ]
Error: Failed to resolve import "./segments" from "src/lib/segments.test.ts". Does the file exist?
FAIL src/lib/time.test.ts [ src/lib/time.test.ts ]
Error: Failed to resolve import "./time" from "src/lib/time.test.ts". Does the file exist?

 Test Files  3 failed (3)
      Tests  no tests
```

Expected and correct — none of the three modules existed yet.

**GREEN** — `cd web && npm test` after writing `segments.ts`, `time.ts`, `SlaChip.tsx`:

```
 ✓ src/api/client.test.ts (10 tests)
 ✓ src/auth/capabilities.test.ts (7 tests)
 ✓ src/lib/segments.test.ts (12 tests)
 ✓ src/lib/time.test.ts (11 tests)
 ✓ src/components/SlaChip.test.tsx (13 tests)
 ✓ src/index.css.test.ts (4 tests)
 ✓ src/lib/cn.test.ts (3 tests)
 ✓ src/components/ui/Avatar.test.tsx (4 tests)
 ✓ src/auth/SessionContext.test.tsx (6 tests)
 ✓ src/routes.test.tsx (11 tests)
 ✓ src/components/ui/Button.test.tsx (4 tests)
 ✓ src/components/ui/Dialog.test.tsx (7 tests)
 ✓ src/theme/ThemeContext.test.tsx (7 tests)
 ✓ src/components/ui/Dropdown.test.tsx (5 tests)
 ✓ src/components/AppShell.test.tsx (11 tests)
 ✓ src/api/types.generated.test.ts (2 tests)
 ✓ src/features/login/LoginPage.test.tsx (6 tests)

 Test Files  17 passed (17)
      Tests  123 passed (123)
```

## Defect found and fixed: `SlaChip.test.tsx`'s "ticks without a reload"

Running the brief's Step 5 `SlaChip.test.tsx` unmodified against the brief's Step 7
`SlaChip.tsx` unmodified produced a **real failure**, not just an act() warning:

```
FAIL src/components/SlaChip.test.tsx > SlaChip > ticks without a reload
TestingLibraryElementError: Unable to find an element with the text: 03:00.
...
<span ...>03:05</span>
```

plus five `Warning: An update to SlaChip inside a test was not wrapped in act(...)`
messages.

Root cause: the test calls `vi.advanceTimersByTime(5000)` directly (not wrapped in
`act(...)`). `SlaChip`'s `setInterval` callback fires and calls `setNow`, but React 18 +
`@testing-library/react` (createRoot/concurrent mode) doesn't guarantee that a state
update triggered by a raw timer callback commits synchronously unless it happens inside
`act()`. The assertion ran before the update flushed, so it still saw `03:05`, and React's
act-environment check (armed by RTL by default) logged the warning on every such update
regardless.

I considered two fixes:
1. **Production-side**: wrap the interval's `setState` in `flushSync` (`react-dom`). This
   made the assertion pass but did **not** silence the `act()` warnings — `flushSync`
   forces a synchronous commit but doesn't register as "acting" with React's dev-mode
   act-tracking, so the warnings persisted. It also adds a test-motivated import to
   production code for a problem that's really about how the test drives fake timers.
2. **Test-side** (adopted): wrap `vi.advanceTimersByTime(5000)` in `act(() => { ... })`,
   importing `act` from `@testing-library/react`. This is the standard pattern for
   interval-driven state updates under fake timers, fixes both the failure and every
   `act()` warning, and changes no assertion, value, or boundary — only how the timer
   advance is driven.

I went with fix 2, so `web/src/components/SlaChip.tsx` is **exactly** the brief's Step 7
code, unmodified. The only deviation from the brief's literal text is a 2-line diff in
`SlaChip.test.tsx`:

```diff
-import { render, screen } from '@testing-library/react'
+import { act, render, screen } from '@testing-library/react'
...
-    vi.advanceTimersByTime(5000)
+    act(() => {
+      vi.advanceTimersByTime(5000)
+    })
```

with a comment in the test explaining why. Per the task instructions ("do not bend the
code to make it pass... report the defect"): this isn't the wrong-test-assertion case the
instructions warn about — the assertion (`03:00` after 5s) is correct — it's a missing
`act()` wrapper, a test-authoring omission independent of any tested value. I'm reporting
it here rather than silently shipping it unremarked, per instructions, but did not change
any behavior, boundary, or expected value to make it pass.

## Minor discrepancy (not fixed, informational only)

The brief's Step 8 says "Expected: PASS — 13 segment tests, 11 time tests, 13 SLA tests."
The brief's own Step 1 `segments.test.ts` (which I copied verbatim) contains **12** `it(...)`
blocks, not 13 (`isGsm7`: 3, `segmentCount`: 8, `charCount`: 1). The test run confirms 12.
This is just the brief's summary prose miscounting its own embedded test file — the literal
test code and all its assertions are unchanged and all pass. No action taken; flagging per
"report a discrepancy rather than silently reconciling."

## The server cross-check (Step 9)

Command:

```bash
cd server && ../.venv/Scripts/python.exe -c "from app.domain.sms import segment_count as s; print([s('a'*160), s('a'*161), s('a'*306), s('a'*307), s('a'*159+'€'), s('日'*70), s('日'*71), s('\U0001F600'*35), s('\U0001F600'*36)])"
```

Output: `[1, 2, 2, 3, 2, 1, 2, 1, 2]`

| Case | Server | TypeScript (`segmentCount`, asserted in `segments.test.ts`) |
|---|---|---|
| `'a'*160` | 1 | 1 |
| `'a'*161` | 2 | 2 |
| `'a'*306` | 2 | 2 |
| `'a'*307` | 3 | 3 |
| `'a'*159 + '€'` | 2 | 2 |
| `'日'*70` | 1 | 1 |
| `'日'*71` | 2 | 2 |
| `'\U0001F600'*35` (emoji×35) | 1 | 1 |
| `'\U0001F600'*36` (emoji×36) | 2 | 2 |

All nine boundaries agree exactly between server and client. No mismatch found — no defect
to report on the segment counter itself.

## `npx tsc -b`

Clean, no output, no warnings. `strict: true` and `noUnusedLocals: true` are both set in
`web/tsconfig.json` and the build passed under them with no `any` and no `@ts-ignore`.

## Files changed

- `web/src/lib/segments.ts` (new)
- `web/src/lib/segments.test.ts` (new)
- `web/src/lib/time.ts` (new)
- `web/src/lib/time.test.ts` (new)
- `web/src/components/SlaChip.tsx` (new)
- `web/src/components/SlaChip.test.tsx` (new)

## Self-review findings

- **Completeness**: 12 segment tests (see discrepancy note above — brief's own test file has
  12, not 13), 11 time tests, 13 SLA tests, all passing. The chip's `useEffect` interval
  ticks it every second without a reload (covered by the "ticks without a reload" test).
- **Quality**: `segmentCount` agrees with the server on all 9 checked boundaries (Step 9,
  above). The overdue label uses `−` (U+2212, confirmed via the literal character in
  `MINUS` and asserted with `'−' + '04:12'` in the test). `slaState` returns `null` with no
  `dueAt` (test: "is null with no due date") and returns `{ tone: 'done', label: 'done' }`
  once `answered` (test: "is done once the conversation has been answered") — checked
  before the `dueAt` null-check, so an answered conversation with no `dueAt` still renders
  `done` rather than nothing, matching "reading `done` once answered" in the brief.
- **Discipline**: no date library added; `time.ts` is hand-rolled per the brief. Nothing
  beyond the four specified files (plus their three test files). No stray tokens, no hex
  colors — only `okBg/okText`, `warnBg/warnText`, `dangerBg/dangerText`,
  `timerDoneBg/timerDoneText`, all pre-existing in `tailwind.config` and already used by
  `Badge.tsx`. Chip radius is `rounded-md` (6px) per the mockup, not 8px.
- **Testing**: full-suite output is pristine — 123/123 passing, no `act()` warnings, no
  unhandled rejections, confirmed by re-running `npm test` after the `SlaChip.test.tsx` fix.

## Issues or concerns

1. **Defect fixed in the given `SlaChip.test.tsx`** (missing `act()` wrap around
   `vi.advanceTimersByTime`) — detailed above. Production `SlaChip.tsx` is untouched from
   the brief; only the test file has a 2-line diff plus an explanatory comment.
2. **Minor prose/test-count mismatch** in the brief's Step 8 (says 13 segment tests, the
   brief's own embedded test file has 12) — informational only, no code impact.

Neither issue required bending any assertion, boundary number, or token name — both are
reported as found, per instructions.
