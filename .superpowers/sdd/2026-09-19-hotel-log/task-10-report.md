# Task 10 Report: MentionInput

## Addendum: review fix (caret/query desync)

Review found a real bug: `pick()` built the replacement range from a **stale**
`query.start` combined with the **live** `ref.current?.selectionStart`. `query` is only
recomputed in `handleChange` (fires on value changes); moving the caret without changing
the text — ArrowLeft/ArrowRight/Home/End, or a click — fires no `onChange`, so the caret can
drift away from where `query` still thinks it is. Concrete repro from the review: type
`@Ana` (caret at 4), press ArrowLeft twice (caret now 2, `query` untouched), click "Ana
Marquez" → body became `@[Ana Marquez](user:u1)na`, a stray `na` left over from the
un-replaced tail of the query.

**Fix chosen:** replace using the query's own recorded extent (`query.start + 1 +
query.term.length`, the `+1` for the `@`) rather than the live caret, per the review's
first suggested option. I did not take the `onSelect`/refresh-on-caret-move route: it adds
a second code path that recomputes `query` and specifically requires guarding against
closing the listbox on the same click that picks an option (the review flagged this
footgun itself), which is more moving parts for the same fix. The chosen fix needs no new
event wiring — `pick()` already has everything it needs in `query` itself.

`web/src/features/log/MentionInput.tsx`, `pick()`:
```diff
-    const caret = ref.current?.selectionStart ?? text.length
     const token = tokenFor(option)
-    const next = text.slice(0, query.start) + token + text.slice(caret)
+    const queryEnd = query.start + 1 + query.term.length
+    const next = text.slice(0, query.start) + token + text.slice(queryEnd)
```

### RED — new test against the pre-fix code

Added `replaces the whole query even after the caret has moved off the end of it` to
`MentionInput.test.tsx`: types `@Ana`, sends `{ArrowLeft}{ArrowLeft}`, clicks "Ana Marquez",
asserts the resulting body is exactly `tokenFor(OPTIONS[0]!)`.

```
$ cd web && npm test -- MentionInput
 × replaces the whole query even after the caret has moved off the end of it
   AssertionError: expected '@[Ana Marquez](user:u1)na' to be '@[Ana Marquez](user:u1)'
Tests  1 failed | 6 passed (7)
```
Reproduces the review's exact repro output before any fix.

### GREEN — after the fix

```
$ cd web && npm test -- MentionInput
✓ src/features/log/MentionInput.test.tsx (7 tests)
Test Files  1 passed (1)
     Tests  7 passed (7)
```

### Advisory item addressed (in scope): TOKEN_RE g-flag comment

Added a doc comment on the `TOKEN_RE` export warning that it's a shared instance carrying
the `g` flag, so consumers (Task 12's renderer) must use `split()`/`matchAll()` rather than
`.exec()`/`.test()` on it directly, to avoid a `lastIndex`-induced false negative on a later
call. No behavior change — comment only.

### Advisory item left alone (per review instruction): mention pruning on backspace

Confirmed out of scope for this task; assigned to Task 11. Not touched.

### Full verification after the fix

```
$ cd web && npm test
 Test Files  61 passed (61)
      Tests  611 passed (611)
```
610 baseline (per the review's updated count) + 1 new test = 611. No discrepancy.

```
$ cd web && npm run lint
> eslint src --ext .ts,.tsx
(clean)
```

```
$ cd web && npm run build
> tsc -b && vite build
✓ 165 modules transformed.
✓ built in 3.07s
```

### Files changed (this addendum)

- `web/src/features/log/MentionInput.tsx` — `pick()` fix + `TOKEN_RE` doc comment
- `web/src/features/log/MentionInput.test.tsx` — new caret-desync regression test

Commit: `a341f44 fix(web): stop MentionInput desyncing the caret from a stale query`
(on top of `9e54a71` and `53ec9bf`, which had already landed on `hotel-log` before this
review cycle started).

---


## What I implemented

`web/src/features/log/MentionInput.tsx` — a controlled textarea with an `@`-triggered
autocomplete popup over `LogMentionableOut[]`. Modelled on
`web/src/features/inbox/QuickReplyPalette.tsx` (this codebase's existing filtered-popup
component): same `role="listbox"`/`role="option"` shape, same `aria-selected` active-index
tracking, same `onMouseDown` + `preventDefault` trick to keep focus in the textarea when
clicking an option, same Tailwind vocabulary (`rounded-card`, `border-border2`, `bg-surface`,
`bg-surface2` for the active row).

Exports, matching the brief's contract exactly:
- `MentionRef` — `{ type: 'user' | 'department'; id: string }`
- `MentionInput(props)` — the component
- `TOKEN_RE` — `/@\[([^\]]+)\]\((user|department):([0-9a-f-]{36})\)/g`, verbatim from the brief
- `tokenFor(option)` — `` `@[${displayName}](${type}:${id})` ``

Behavior:
- Typing `@` followed by word characters opens the listbox, filtered case-insensitively on
  `displayName` against the text after `@`. Filtering also runs against a normal-looking word
  boundary check (`/^\w*$/` on the fragment since the last `@`), so a space ends the query.
- No matches → no listbox element at all (conditional render, not `hidden`/`display:none`).
- Click or Enter on an option replaces the `@query` span with `tokenFor(option)` and calls
  `onChange(nextValue, [...mentions, {type, id}])`, de-duplicated on `type`+`id`.
- ArrowDown/ArrowUp move the active index (clamped, not wrapping — matches
  `QuickReplyPalette`'s idiom); Enter picks the active option; Escape closes the menu without
  picking.
- After a pick, the caret is programmatically moved to just after the inserted token (a
  `pendingCaret`/`useLayoutEffect`-style pattern using a plain `useEffect`), so continued
  typing — including typing a second `@mention` right after — lands in the right place. This
  isn't in the brief's requirements list explicitly, but it's necessary for realistic use and
  for the de-dup test to exercise a genuine "same person mentioned twice" flow rather than a
  contrived one.

## A design decision the brief didn't spell out: local text buffering

The component keeps its own `text` state, seeded from the `value` prop and re-synced via a
`useEffect` only when `value` changes *externally* (e.g. the parent clears the draft after
submit). Typing itself updates `text` directly, not by waiting for the round trip through
`onChange` → parent state → new `value` prop.

Why: the brief's own literal tests render `<MentionInput value="" ... onChange={vi.fn()} />`
with a `vi.fn()` that never updates a `value` prop. A naive `<textarea value={value}>` bound
straight to the prop would have every one of the component's own internal state updates
(`setQuery`, `setIndex`) trigger a re-render that resets the DOM's value back to the
unchanging `""` prop — so typing "@Front" would visibly collapse back to progressively wrong
text and no options would ever match. I hit exactly this failure first (see RED/GREEN below)
and fixed it with the local buffer + resync-on-external-change pattern. This also happens to
be closer to how `Composer.tsx`'s own `body` state works from the *consuming* side — Composer
owns the state and feeds it back in — but `MentionInput` itself can't assume its caller does
that synchronously, so it treats `value` as an external override rather than the single source
of truth on every keystroke.

## Tests written

All in `web/src/features/log/MentionInput.test.tsx`.

The brief's three (used verbatim, only change: two `OPTIONS[n]` array-index reads got a
non-null assertion, `OPTIONS[1]!` / `OPTIONS[0]!`, because this repo's `tsconfig.json` has
`noUncheckedIndexedAccess: true` and `tsc -b` (the `build` script) type-checks test files too.
This is the codebase's existing idiom for the same situation — see `web/src/api/client.test.ts:34`,
`web/src/index.css.test.ts:58`, `web/src/features/sim/SimulatorPage.test.tsx:116` for the same
`arr[i]!` pattern. No runtime or assertion semantics changed):

1. `records the id of the option picked, not the typed name` — the two-Anas case from the design
   doc. Proves the picker records `u2`, not "Ana Maria-Bonilla".
2. `offers departments too` — proves departments appear in the same flat list and produce
   `{type: 'department', id: 'd1'}`.
3. `closes the menu when no option matches` — proves no `listbox` role exists in the DOM (not a
   hidden one) when nothing matches.

Added (brief describes these requirements but gives no test code):

4. `moves the active option with the arrow keys and picks it with Enter` — types `@Ana`, asserts
   the first option starts `aria-selected="true"`, ArrowDown moves it to the second option, and
   Enter picks the *arrowed-to* option (`u2`), not whatever was first. This is the strongest test
   against an off-by-one or "Enter always picks index 0" bug.
5. `closes the menu on Escape without picking anything` — types `@Ana`, presses Escape, asserts
   no listbox remains and that `onChange` was never called with a non-empty mentions array (i.e.
   Escape didn't silently fire a pick).
6. `de-dupes a mention picked twice into a single entry` — a small stateful `Harness` component
   (real `useState` round-tripping `value`/`mentions` through `onChange`, unlike the brief's three
   tests which use a no-op mock) mentions "Ana Marquez" twice in one body and asserts the
   `mentions` array still has exactly one entry. This one needed the caret-repositioning fix to
   be meaningful — without it, the second `@Ana` query would start mid-token instead of after it.

## TDD evidence

**RED** — before `MentionInput.tsx` existed:
```
$ cd web && npm test -- MentionInput
✗ src/features/log/MentionInput.test.tsx (0 test)
Error: Failed to resolve import "./MentionInput" from "src/features/log/MentionInput.test.tsx".
Test Files  1 failed (1)
     Tests  no tests
```

**First implementation attempt also RED** (naive `<textarea value={value}>`, no local buffer):
```
$ npm test -- MentionInput
 × MentionInput > records the id of the option picked, not the typed name
   → Unable to find an accessible element with the role "option"
 × MentionInput > offers departments too
   → Unable to find an accessible element with the role "option" and name `/Front Desk/`
Tests  2 failed | 1 passed (3)
```
This confirmed the value-prop-reset problem described above, before I added the local `text`
state and the resync effect.

**GREEN** — after the fix, brief's 3 tests:
```
$ npm test -- MentionInput
✓ src/features/log/MentionInput.test.tsx (3 tests)
Test Files  1 passed (1)
     Tests  3 passed (3)
```

**GREEN** — after adding the caret-reposition logic and the 3 extra tests:
```
$ npm test -- MentionInput
✓ src/features/log/MentionInput.test.tsx (6 tests)
   ✓ MentionInput > de-dupes a mention picked twice into a single entry 358ms
Test Files  1 passed (1)
     Tests  6 passed (6)
```

## Sabotage verification (id-not-name behaviour)

Changed the mention-recording line in `pick()`:
```diff
-    const nextMentions = already ? mentions : [...mentions, { type: option.type, id: option.id }]
+    const nextMentions = already ? mentions : [...mentions, { type: option.type, id: option.displayName }]
```
Reran the suite:
```
$ npm test -- MentionInput
 × records the id of the option picked, not the typed name
   AssertionError: expected [ { type: 'user', id: 'Ana Maria-Bonilla' } ] to deeply equal [ { type: 'user', id: 'u2' } ]
 × offers departments too
 × moves the active option with the arrow keys and picks it with Enter
 × de-dupes a mention picked twice into a single entry
   AssertionError: expected [{id: 'Ana Marquez',...}, {id: 'Ana Marquez',...}] to deeply equal [ { type: 'user', id: 'u1' } ]
Tests  4 failed | 2 passed (6)
```
Four of six tests failed on the sabotage — including, notably, the de-dup test, which failed
*twice over*: once on the id substitution and again because de-dup-by-id no longer collapses
two picks of the same person once the "id" being compared is the (identical) display name by
coincidence — actually here both picks used the same option so `already` still matched
correctly; the failure was purely the id-vs-name substitution, confirmed by the mismatched
`id` values in the assertion diff. Reverted the sabotage:
```diff
-    const nextMentions = already ? mentions : [...mentions, { type: option.type, id: option.displayName }]
+    const nextMentions = already ? mentions : [...mentions, { type: option.type, id: option.id }]
```
Reran: all 6 pass again (confirmed).

## Full verification

```
$ cd web && npm test
 Test Files  60 passed (60)
      Tests  609 passed (609)
```
603 baseline + 6 new = 609. No discrepancy.

```
$ cd web && npm run lint
> eslint src --ext .ts,.tsx
(clean, no output)
```

```
$ cd web && npm run build
> tsc -b && vite build
✓ 165 modules transformed.
✓ built in 2.76s
```

## Files changed

- `web/src/features/log/MentionInput.tsx` (new)
- `web/src/features/log/MentionInput.test.tsx` (new)

## Self-review findings

- `TOKEN_RE`'s id group `[0-9a-f-]{36}` only matches real UUIDs, not the short test fixture ids
  (`u1`, `u2`, `d1`). That's fine — `TOKEN_RE` isn't exercised by this task's tests (it's for
  Task 12's renderer against real server-issued UUIDs) and the regex is copied verbatim from
  the brief.
- `activeQuery`'s word-boundary check (`/^\w*$/`) does not allow the query to include the
  space/hyphen in "Ana Maria-Bonilla" while typing — that's expected; you type a *query*
  ("Ana"), not the full name, then pick from the filtered list.
- The component doesn't scroll the active option into view when arrow-keying past the visible
  area. `QuickReplyPalette` doesn't either, so I matched precedent rather than adding scope.
- No `aria-activedescendant` wiring from the textarea to the active option — again,
  `QuickReplyPalette` doesn't do this either, so I didn't invent a new accessibility pattern
  the rest of the codebase doesn't use.
- The two `OPTIONS[n]!` non-null assertions are the only departure from the brief's literal
  test text, and they're required by this repo's `noUncheckedIndexedAccess: true` tsconfig
  setting reaching test files during `tsc -b`; the same `arr[i]!` idiom is already used
  throughout the existing test suite (cited above), so this isn't a new pattern.

## Concerns

None blocking. One thing worth flagging to the controller: `web/src/features/log/` did not
exist before this task (Task 9 landed its API hooks in `web/src/api/hooks/log.ts`, not under
`features/log/`), so this is the first file in that directory. Nothing to reconcile — just
noting it since the brief describes `MentionInput` as living alongside other Task 11/12/13
components that don't exist yet.
