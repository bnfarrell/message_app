# Task 4: UI primitives — Report

## What I implemented

All ten primitives specified in the brief, exactly as given (literal code from the brief), plus the barrel export:

- `web/src/components/ui/Spinner.tsx`
- `web/src/components/ui/Button.tsx`
- `web/src/components/ui/Input.tsx`
- `web/src/components/ui/Textarea.tsx` (plain function component, no `forwardRef` — per the brief and the task instructions, that conversion belongs to the composer task)
- `web/src/components/ui/Badge.tsx`
- `web/src/components/ui/Avatar.tsx` (+ exported `initialsOf` helper)
- `web/src/components/ui/EmptyState.tsx`
- `web/src/components/ui/Dialog.tsx`
- `web/src/components/ui/Dropdown.tsx`
- `web/src/components/ui/Toast.tsx` (`ToastProvider` + `useToast`)
- `web/src/components/ui/index.ts` — re-exports all of the above

Test files (also literal from the brief):
- `web/src/components/ui/Button.test.tsx`
- `web/src/components/ui/Dialog.test.tsx`
- `web/src/components/ui/Dropdown.test.tsx`
- `web/src/components/ui/Avatar.test.tsx`

No deviation from the brief's code was needed — every test in the brief passed as written against the brief's own implementation, including the two focus-management assertions (Dialog focus-in, Dropdown focus-return). No defect found in this task's literal text.

## What I tested and the results

Followed the brief's TDD steps precisely.

### TDD evidence

**RED** — `cd web && npx vitest run src/components/ui` (run before any component files existed, only the four test files):

```
FAIL src/components/ui/Avatar.test.tsx  Error: Failed to resolve import "./Avatar" from "src/components/ui/Avatar.test.tsx". Does the file exist?
FAIL src/components/ui/Button.test.tsx  Error: Failed to resolve import "./Button" from "src/components/ui/Button.test.tsx". Does the file exist?
FAIL src/components/ui/Dialog.test.tsx  Error: Failed to resolve import "./Dialog" from "src/components/ui/Dialog.test.tsx". Does the file exist?
FAIL src/components/ui/Dropdown.test.tsx  Error: Failed to resolve import "./Dropdown" from "src/components/ui/Dropdown.test.tsx". Does the file exist?

 Test Files  4 failed (4)
      Tests  no tests
```

Expected and correct: none of the four modules existed yet, so Vite's import resolution fails immediately — exactly the "FAIL — none of the four modules resolve" the brief predicted.

**GREEN** — after writing all ten primitives and the barrel, `cd web && npx vitest run src/components/ui`:

```
 ✓ src/components/ui/Avatar.test.tsx (4 tests) 22ms
 ✓ src/components/ui/Button.test.tsx (4 tests) 117ms
 ✓ src/components/ui/Dialog.test.tsx (5 tests) 223ms
 ✓ src/components/ui/Dropdown.test.tsx (5 tests) 368ms

 Test Files  4 passed (4)
      Tests  18 passed (18)
```

### Full suite (Step 8)

`cd web && npm test`:

```
 ✓ src/index.css.test.ts (4 tests) 6ms
 ✓ src/api/types.generated.test.ts (2 tests) 433ms
 ✓ src/api/client.test.ts (10 tests) 19ms
 ✓ src/lib/cn.test.ts (3 tests) 1ms
 ✓ src/components/ui/Avatar.test.tsx (4 tests) 35ms
 ✓ src/components/ui/Button.test.tsx (4 tests) 117ms
 ✓ src/components/ui/Dialog.test.tsx (5 tests) 207ms
 ✓ src/components/ui/Dropdown.test.tsx (5 tests) 498ms

 Test Files  8 passed (8)
      Tests  37 passed (37)
```

37 total = the brief's predicted 18 primitive tests + Tasks 1-3's 19 (4+2+10+3).

### Build check

`cd web && npx tsc -b` — no output, exit clean. No `any`, no `@ts-ignore` anywhere in the new files (grepped to confirm).

### act() warnings

Full-suite output above is pristine — no `Warning: An update to ... was not wrapped in act(...)` lines anywhere, including in the Dialog and Dropdown files where focus/effect timing makes such warnings easy to introduce.

## Files changed

- `web/src/components/ui/Spinner.tsx` (new)
- `web/src/components/ui/Button.tsx` (new)
- `web/src/components/ui/Button.test.tsx` (new)
- `web/src/components/ui/Input.tsx` (new)
- `web/src/components/ui/Textarea.tsx` (new)
- `web/src/components/ui/Badge.tsx` (new)
- `web/src/components/ui/Avatar.tsx` (new)
- `web/src/components/ui/Avatar.test.tsx` (new)
- `web/src/components/ui/EmptyState.tsx` (new)
- `web/src/components/ui/Dialog.tsx` (new)
- `web/src/components/ui/Dialog.test.tsx` (new)
- `web/src/components/ui/Dropdown.tsx` (new)
- `web/src/components/ui/Dropdown.test.tsx` (new)
- `web/src/components/ui/Toast.tsx` (new)
- `web/src/components/ui/index.ts` (new)

## Self-review findings

- **Completeness:** all 10 primitives present (Button, Input, Textarea, Badge, Avatar, Spinner, EmptyState, Dialog, Dropdown, Toast). Barrel exports all of them plus `initialsOf` and `useToast`/`ToastProvider`. All four brief-specified test files present.
- **Shape language:** `h-11` (44px) used on Button, Input, and the Dropdown trigger button. `rounded-card` (10px) used on the Dialog panel; `rounded`/`rounded-md` (8px/6px) elsewhere. 1px borders throughout (`border`). Grepped the whole directory for `shadow` — zero hits, confirming no shadows anywhere.
- **Accent discipline:** `bg-accent` appears only in `Button`'s `primary` variant string and in `Spinner`'s `border-t-accent` (the spinner's spin indicator, which is the brief's own literal code, not an addition of mine — it's a loading indicator, not a decorative background fill).
- **Discipline:** grepped for `forwardRef`, `: any`, `@ts-ignore` — none present. No extra props or speculative flexibility added; every line traces to the brief.
- **Accessibility:** `Dialog` captures `document.activeElement` before moving focus in, focuses the first focusable element in the panel (or the panel itself) on open, and restores focus to the captured element in its effect cleanup on close — verified by the "moves focus into the dialog" test passing without flakiness. `Dropdown`'s `close()` sets `open` false and calls `trigger.current?.focus()`, covering both the Escape path and the item-invoked-`close` path; outside-click is handled via a `mousedown` listener scoped to `!root.contains(target)`.
- **Test quality:** all tests assert observable behavior (roles, accessible names, attributes, focus, disabled state) rather than internals. No `act()` warnings in any run.

## Issues or concerns

None. All brief code worked as specified in jsdom; no defect found in this task's literal text (unlike three of the prior four tasks). Windows CRLF-conversion warnings appeared during `git add`/`commit` (core.autocrlf normalizing LF→CRLF) — cosmetic, not a code issue, and consistent with how this repo already handles line endings on Windows checkouts.

---

## Fix round 1

Two findings from review. `Badge`/`Avatar`'s `rounded-md` (6px) was reviewed and confirmed correct per the mockups (three-radius scale, not two) — no change made there.

### Finding 1 — `Dialog`'s focus-management effect depended on `onClose`

**Root cause:** the effect was `useEffect(() => {...}, [open, onClose])`. Real callers pass `onClose={() => setOpen(false)}` — a new function identity every render — so any parent re-render while the dialog was open replayed the whole capture-and-focus body: cleanup restored focus to the pre-open element, then the body re-ran, recaptured that (now-current) `document.activeElement`, and refocused the panel's first focusable control, regardless of what the user was actually interacting with.

**New test added first (`Dialog.test.tsx`):** a `Wrapper` component holding `open` and a controlled `notes` field, passing `onClose={() => setOpen(false)}` inline (fresh identity each render) so typing in the field forces exactly the re-render pattern a real form dialog would produce. Focuses the `Notes` textarea, types into it, and asserts it keeps focus.

**RED** — `npx vitest run src/components/ui/Dialog.test.tsx` (test added, fix not yet applied):

```
❯ src/components/ui/Dialog.test.tsx (7 tests | 1 failed)
   × Dialog > does not steal focus from a field the user is editing when the parent re-renders with a new onClose identity
     → expect(element).toHaveFocus()

Expected element with focus:
  <textarea aria-label="Notes"> h </textarea>
Received element with focus:
  <button aria-label="Close" ...>✕</button>

 Test Files  1 failed (1)
      Tests  1 failed | 6 passed (7)
```

This confirms the exact defect: typing forced a re-render, the effect replayed, and focus jumped away to the dialog's first focusable element (the header's Close button, first in DOM order) instead of staying on the field being edited.

**Fix:** added an `onCloseRef` updated by its own `useEffect(() => { onCloseRef.current = onClose }, [onClose])`, and changed the focus-management effect's dependency array to `[open]` only, reading `onCloseRef.current()` from the Escape handler instead of closing over `onClose` directly. The effect's capture-and-focus body and its restore-on-cleanup now run exactly once per open→close transition, never on an in-between re-render.

Also confirmed while in the file: the Escape `keydown` listener is removed in the effect's cleanup (which fires on unmount as on any other dependency change), and added a regression test that unmounts the dialog while `open` and asserts it doesn't throw and that a post-unmount Escape keypress no longer calls `onClose` (the listener is gone).

**GREEN** — `npx vitest run src/components/ui/Dialog.test.tsx`:

```
✓ src/components/ui/Dialog.test.tsx (7 tests) 334ms

 Test Files  1 passed (1)
      Tests  7 passed (7)
```

### Finding 2 — `Toast`'s timer was never cleared

`push()`'s `setTimeout` id was discarded, so an unmount before the 5s auto-dismiss elapsed left a dangling timer that would later call `setState` on an unmounted component (a silent no-op under React 18, but wrong). Fixed by keeping a `useRef(new Set<ReturnType<typeof setTimeout>>())` of pending timer ids, adding each id when scheduled and removing it when it fires, and clearing/emptying the set in a mount-once `useEffect`'s cleanup so any timers still pending at unmount are cancelled.

No dedicated test added for this — it's not independently observable from outside the component without reaching into internals or mocking timers in a way that would test implementation rather than behavior, and the task treated it as a minor, low-risk cleanup rather than a defect requiring its own regression test.

### Full verification after both fixes

`cd web && npx vitest run src/components/ui`:

```
✓ src/components/ui/Avatar.test.tsx (4 tests) 34ms
✓ src/components/ui/Button.test.tsx (4 tests) 90ms
✓ src/components/ui/Dialog.test.tsx (7 tests) 334ms
✓ src/components/ui/Dropdown.test.tsx (5 tests) 452ms

 Test Files  4 passed (4)
      Tests  20 passed (20)
```

No `act()` warnings in this output.

`cd web && npm test` (full suite, now also picking up the concurrent auth-task's files, which are outside this task's scope):

```
✓ src/index.css.test.ts (4 tests)
✓ src/api/types.generated.test.ts (2 tests)
✓ src/lib/cn.test.ts (3 tests)
✓ src/auth/capabilities.test.ts (7 tests)
✓ src/api/client.test.ts (10 tests)
✓ src/components/ui/Avatar.test.tsx (4 tests)
✓ src/components/ui/Button.test.tsx (4 tests)
✓ src/auth/SessionContext.test.tsx (6 tests)
✓ src/components/ui/Dialog.test.tsx (7 tests)
✓ src/components/ui/Dropdown.test.tsx (5 tests)

 Test Files  10 passed (10)
      Tests  52 passed (52)
```

The only console output is two React Router future-flag warnings from the other agent's `SessionContext.test.tsx` — not an `act()` warning, and not in code this task touched.

`cd web && npx tsc -b` — no output, clean.

### Files changed in this fix round

- `web/src/components/ui/Dialog.tsx` — `onCloseRef` pattern; effect now depends on `[open]` only.
- `web/src/components/ui/Dialog.test.tsx` — added the focus-retention regression test and the unmount/listener-cleanup test.
- `web/src/components/ui/Toast.tsx` — tracks and clears pending toast-dismiss timers on unmount.

### Commit

`e6e486f` — `fix(web): stop Dialog re-stealing focus on re-render; clear Toast timers`
