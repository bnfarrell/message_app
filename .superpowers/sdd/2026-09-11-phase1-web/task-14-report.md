# Task 14 report — Composer: quick replies, assets, segment counter, optimistic send, retry

## What I implemented

Per the brief's file list, in TDD order:

- `web/src/api/hooks/content.ts` — `useQuickReplies`, `useRenderQuickReply`, `useAssets`, `useCategories` (verbatim from the brief; `qk.quickReplies`/`qk.assets`/`qk.categories` already existed in `queryKeys.ts` from an earlier task).
- `web/src/api/hooks/conversations.ts` — added `useSendMessage` (optimistic) and `useRetryMessage` (verbatim from the brief).
- `web/src/features/inbox/QuickReplyPalette.tsx` — `filterQuickReplies` (exported for its own test) and `QuickReplyPalette` (verbatim from the brief).
- `web/src/features/inbox/AssetPicker.tsx` — verbatim from the brief.
- `web/src/features/inbox/Composer.tsx` — the brief's implementation, with two changes: (1) a fix to the Escape/palette-dismiss defect described below, and (2) the `can('reply')` gate added per the dispatch (not in the brief, since it was cut before the brief was written).
- `web/src/components/ui/Textarea.tsx` — converted to `forwardRef`, verbatim from the brief.
- `web/src/features/inbox/ConversationView.tsx` — mounted `<Composer>` after the timeline, wired `onRetry` into `MessageBubble` for `failed`/`undelivered` messages, per the brief's Step 9.
- Tests: `web/src/features/inbox/QuickReplyPalette.test.tsx` and `web/src/features/inbox/Composer.test.tsx`, taken verbatim from the brief except for the scaffolding fixes below, plus one added test for the `can('reply')` gate.

## Defects found and fixed

Four real defects surfaced during GREEN. None were fixed by bending correct code to a wrong assertion — each is a genuine bug in the brief's literal text, verified before touching anything.

**1. Production defect — `Composer.tsx`'s palette `onClose` cleared the draft.**
The brief's Step 8 code had `onClose={() => setBody('')}`. This directly contradicts the brief's own spec text ("Escape closes and leaves the typed text alone", §5.3) and its own test (`closes the palette on Escape and keeps the typed text`, which asserts `box` still has value `/wi` after Escape). Running the test as-written against the brief's own implementation failed with `Received: ""`. Root cause: the palette's visibility was derived purely from `body` content with no separate "explicitly dismissed" flag, so there was no way to hide the palette without also clearing the text that makes `paletteOpen` true. Fix: added a `paletteDismissed` boolean state, set by `onClose`, cleared on every textarea `onChange` (so typing again reopens the palette naturally). Verified live (see below).

**2. Test scaffolding defect — `routes()`'s key-matching order made the `render` override unreachable.**
The mock's generic fallback does `Object.keys(table).find((k) => url.includes(k))`. Because the render endpoint's URL (`quick-replies/<id>/render`) contains the substring `quick-replies`, and `'quick-replies'` is inserted into `table` before the test's `render` override, the lookup always matched `'quick-replies'` first and returned the quick-reply list instead of the `RenderedQuickReply` the test intended. This made `render.mutate`'s `onSuccess` call `setBody(undefined)` (since an array has no `.body`), which then threw `Cannot read properties of undefined (reading 'startsWith')` on next render — an uncaught exception traced directly to this scaffolding bug, not to `Composer.tsx`. Fix: added a special-cased branch for `POST .../render`, mirroring the existing special case for `POST .../messages`, checked before the generic table lookup.

**3. Test scaffolding defect — `toHaveValue(expect.stringContaining(...))` never works in this `jest-dom` version.**
`@testing-library/jest-dom@6.9.1`'s `toHaveValue` implementation (`compareAsSet`) does a strict `===` comparison, not `expect`'s asymmetric-matcher-aware `equals`. Passing `expect.stringContaining(...)` as the expected value can never match a real string via `===`. Two consequences:
- `appends a short link when an asset is picked` used this pattern positively and **failed** every time, regardless of implementation correctness (confirmed: the actual textarea value did contain `/a/wifi1`, but the matcher structurally cannot see that).
- `inserts the server-rendered body...` used `.not.toHaveValue(expect.stringContaining('{{'))`, which is the same pattern negated — since `===` is always false, `.not` always passes, so this assertion was verifying nothing (a "test that passes against buggy code" in the making, since a client that DID leak `{{` would still pass it).
Fix: replaced both with direct `.value` checks (`.toContain` / `.not.toContain`) on the textarea element.

**4. Test scaffolding defect — the inline `WebSocket` stub classes were missing `static OPEN = 1`.**
`src/api/ws.ts`'s `send()` gates on `socket.current?.readyState === WebSocket.OPEN`. The two inline stub classes in `Composer.test.tsx` (in `beforeEach` and inside the presence test) set `readyState = 1` but never defined a static `OPEN`, so `WebSocket.OPEN` was `undefined` and `1 === undefined` is always false — no presence frame was ever actually sent, only appeared to be. `src/api/ws.test.tsx` (Task 11's own suite) uses the correct pattern (`static OPEN = 1` on its `FakeSocket`), confirming this is the established convention the brief's inline stubs missed. Fixed both classes to add `static OPEN = 1`.

## The `can('reply')` gate

Per the dispatch (added after the brief was cut): `Composer` calls `useSession()` and, after all hooks run (Rules of Hooks — hooks are called unconditionally every render), returns `null` before any JSX if `!can('reply')`. `corporate` has `view_all_conversations` and `add_note` but not `reply`. I added one test (`renders nothing for a role without the reply capability`) asserting no textbox and no Send button render for a `corporate` session. This is the only test added beyond the brief's literal 31.

## What I tested and the results

**TDD evidence.**

RED (Step 5, before any implementation files existed):
```
cd web && npx vitest run src/features/inbox/QuickReplyPalette.test.tsx src/features/inbox/Composer.test.tsx
```
```
FAIL src/features/inbox/Composer.test.tsx
Error: Failed to resolve import "./Composer" from "src/features/inbox/Composer.test.tsx". Does the file exist?
FAIL src/features/inbox/QuickReplyPalette.test.tsx
Error: Failed to resolve import "./QuickReplyPalette" from "src/features/inbox/QuickReplyPalette.test.tsx". Does the file exist?
Test Files  2 failed (2)
     Tests  no tests
```
Expected: neither module existed yet, so both files fail to resolve — matches the brief's "Expected: FAIL — neither module resolves."

First GREEN attempt (after implementing all files exactly per the brief, before the defect fixes) surfaced 4 real failures out of 31 (`closes the palette on Escape...`, `inserts the server-rendered body...`, `appends a short link...`, `reports composing presence...`) — these are exactly defects 1–4 above, each individually re-run and root-caused before fixing (see per-test isolated runs in the session, e.g. `npx vitest run src/features/inbox/Composer.test.tsx -t "closes the palette on Escape"` reproducing `Received: ""` from the `onClose={() => setBody('')}` bug).

GREEN (after the four fixes, plus the added `can('reply')` test):
```
cd web && npx vitest run src/features/inbox/QuickReplyPalette.test.tsx src/features/inbox/Composer.test.tsx
```
```
✓ src/features/inbox/QuickReplyPalette.test.tsx (15 tests)
✓ src/features/inbox/Composer.test.tsx (17 tests)
Test Files  2 passed (2)
     Tests  32 passed (32)
```
(15 = 9 filter + 6 palette; 17 = 16 brief tests + 1 added `can('reply')` test. The brief's Step 10 comment says "10 filter tests" — the brief's own test file literally contains 9 `it()` blocks under `describe('filterQuickReplies', ...)`; this is a miscount in the brief's prose, not a missing test — all 9 are present and pass.)

Full suite:
```
cd web && npm test
```
```
Test Files  26 passed (26)
     Tests  222 passed (222)
```
No `act()` warnings, no unhandled rejections in the output.

`npx tsc -b`: clean, no output, exit 0.

## The live verification

Both the Flask server (127.0.0.1:5000) and the Vite dev server (localhost:5173) were already running from a prior session, already seeded, and I was already signed in as `ava@hvh.test`. I drove the running app with the Playwright browser tools rather than starting fresh.

**What I observed, checked live:**
- Opened room 412 (Sarah Chen). The composer mounted: textarea, Attach button, Send button.
- Typed `/` in the empty box — the palette opened, listing all ~15 seeded quick replies (`/breakfast`, `/gym`, `/wifi`, `/bill`, `/shuttle`, `/towels`, `/late`, `/restaurant`, `/eng`, `/checkout`, `/thanks`, `/pool`, `/parking`, `/sorry`, `/housekeeping`), with the raw `{{guest_first_name}}`/`{{room_number}}` tokens visible in the *unrendered* list (as expected — those are the templates, not what gets sent).
- Typed `/wi` — filtered to `/wifi` first (shortcut-prefix match), then `/gym`, `/bill`, `/eng`, `/parking` (body/title substring matches on "wi" — matches the palette's documented ranking).
- Pressed Enter on `/wifi` — the textarea filled with the **server-rendered** body: `"Hi Sarah — the network is Harbourview-Guest, no password needed. If it drops, toggle WiFi off and on."` — naming Sarah, zero `{{` present. Confirmed via `document.querySelector('textarea').value`.
- Clicked Attach → WiFi card → the short link `http://localhost:5173/a/hqrzya` was appended to the draft.
- Segment counter read `101 chars · 2 segments` in `text-warnText` (amber) — the interpolated body contains an em dash, which is outside GSM-7, so it correctly fell to the UCS-2 count (70-char first segment) rather than the GSM-7 160-char threshold; confirmed the counter uses the Task 10 helpers, not separate arithmetic, since this UCS-2 boundary behavior is `segments.ts`'s, not something I reimplemented.
- Clicked Send — the message appeared and, without a page reload, progressed to **Delivered** (by the time I re-snapshotted, the worker + WebSocket had already carried it through `queued → sent → delivered`).
- Opened Tom Becker's conversation (room 516, phone `+15552000000`, ends in `0000`) — the seed already has a message there in **Failed · 30007** state with a working **Retry** button. Clicked Retry; the button re-rendered (new DOM node), confirming the mutation fired and the conversation refetched — it correctly stayed **Failed** afterward, since that phone number is hard-coded to fail every delivery attempt (this is the mock SMS adapter's designed behavior, not a bug).
- Re-verified the Escape fix directly against the running app (not just the test): typed `/wi` in Tom's composer, pressed Escape — `document.querySelector('textarea').value` was still `"/wi"` and `document.querySelector('[role="listbox"]')` was gone. Matches the fixed defect above.

**What I could not run, and why:** the opted-out-guest 422 rejection path. I checked the dispatch's claim that "the seed has no opted-out guest" before accepting it, since I was told to verify rather than trust such claims — and it's not quite right as stated: `seed/seed.py` does create one opted-out guest, Lena Park (`+15553104411`, `SmsConsentStatus.opted_out`). However, her stay is seeded as `checked_out`, and the seed's conversation-generation loop only draws from `in_house` stays (`status == checked_in`) when assigning the 29 randomly-distributed conversations, plus Tom's explicit one. Lena is excluded from that pool, so she has a guest record but **no conversation** — there is no thread in the seeded data where the composer can be opened against an opted-out guest. So the dispatch's practical conclusion (this path can't be exercised live) holds, even though its literal wording ("no opted-out guest") undersold why. This path is covered by the two Composer unit tests (`shows the consent warning but stays enabled...` and `restores the draft and shows the server reason when a send is rejected`), both passing.

## `npx tsc -b`

Clean. No output, no warnings, exit 0.

## Files changed

- `web/src/api/hooks/content.ts` (new)
- `web/src/api/hooks/conversations.ts` (added `useSendMessage`, `useRetryMessage`)
- `web/src/features/inbox/QuickReplyPalette.tsx` (new)
- `web/src/features/inbox/QuickReplyPalette.test.tsx` (new)
- `web/src/features/inbox/AssetPicker.tsx` (new)
- `web/src/features/inbox/Composer.tsx` (new)
- `web/src/features/inbox/Composer.test.tsx` (new)
- `web/src/components/ui/Textarea.tsx` (converted to `forwardRef`)
- `web/src/features/inbox/ConversationView.tsx` (mounted `Composer`, wired `onRetry`)

## Self-review findings

- **Completeness:** all 9 filter tests, 6 palette tests, and 17 composer tests (16 from the brief + 1 added for the `can('reply')` gate) pass. The brief's Step 10 prose says "10 filter tests" but its own test file has 9 `describe('filterQuickReplies')` blocks — a miscount in the brief's text, not a missing test; flagged above rather than silently reconciled.
- **Quality:**
  - Palette opens only on a leading `/` in an otherwise-empty-of-spaces/newlines draft — verified by both the unit test and live (`either/or` does not open it; the mid-sentence guard is unchanged from the brief).
  - Escape keeps the typed text — was broken in the brief's given code, now fixed and verified both by test and live browser check.
  - A failed send removes the optimistic bubble and restores the draft text — verified by the `restores the draft...` test (`onError` in `submit()` restores `trimmed`; the mutation hook's own `onError` strips the optimistic entry from the cache).
  - The counter uses `segmentCount`/`charCount` from `lib/segments.ts` (Task 10) — no separate arithmetic in `Composer.tsx`.
  - Composer is absent for a role without `reply` — verified by the added test and reasoned through the capability map (`corporate` lacks `reply`, keeps `add_note`, which nothing here touches).
- **Discipline:** no client-side token interpolation — the only place `rendered.body` is set is from the `useRenderQuickReply` response; nothing constructs or substitutes `{{...}}` locally. Nothing was added beyond the brief plus the explicitly-requested `can('reply')` gate.
- **Testing:** full suite output is warning-free — no `act()` warnings, no unhandled rejections, across all 222 tests including the 32 new/changed to this task.

## Issues or concerns

None blocking. Two things worth flagging for whoever reviews next:
- The brief's Step 10 comment ("10 filter tests") is off by one against the brief's own literal test code (9). Not a functional defect — just noting it so it isn't mistaken for a missing test later.
- Live-testing the send-to-Sarah flow left one real outbound message in the dev database (`"Hi Sarah — the network is Harbourview-Guest..."` with the WiFi short link, now Delivered) and one live click of Retry on Tom's permanently-failing message (still Failed, as designed). Both are harmless dev-seed-database side effects of the required live verification, not code changes.

---

## Fix report — review round (Set A from Task 12's review, Set B from Task 14's own review)

Two commits: `996d77c` (Set A) and `516c77d` (Set B) — kept separate since they come from different reviews and touch different files, per the dispatch's "your call."

### B1 — palette keydown listener not scoped to "has matches" (Important)

**File:** `web/src/features/inbox/QuickReplyPalette.tsx`

The `useEffect` registering the global `keydown` listener ran unconditionally, before the `matches.length === 0` render guard. A `/`-prefixed draft with no match (`/wifi123`) rendered nothing but still globally called `preventDefault()` on ArrowUp/ArrowDown/Escape — arrow-key cursor movement in the textarea silently broke with nothing on screen to explain why.

**Fix:** moved the zero-match check inside the effect, before the listener is attached:
```ts
useEffect(() => {
  if (matches.length === 0) return
  function onKeyDown(event: KeyboardEvent) { ... }
  document.addEventListener('keydown', onKeyDown)
  return () => document.removeEventListener('keydown', onKeyDown)
}, [matches, index, onPick, onClose])
```

**Covering test:** `QuickReplyPalette.test.tsx` → `does not intercept arrow keys when there are no matches`. Renders the palette with `term="helicopter"` (matches nothing), dispatches a real `KeyboardEvent('keydown', { key: 'ArrowDown', cancelable: true })` on `document`, and asserts `event.defaultPrevented === false`.

**RED (before the fix):**
```
npx vitest run src/features/inbox/QuickReplyPalette.test.tsx -t "does not intercept arrow keys"
```
```
× QuickReplyPalette > does not intercept arrow keys when there are no matches
  → expected true to be false // Object.is equality
  - Expected: false
  + Received: true
```
Expected: the un-fixed handler unconditionally calls `preventDefault()` on ArrowDown regardless of match count, so `defaultPrevented` comes back `true`.

**GREEN (after the fix):**
```
npx vitest run src/features/inbox/QuickReplyPalette.test.tsx
```
```
✓ src/features/inbox/QuickReplyPalette.test.tsx (16 tests)
Test Files  1 passed (1)
     Tests  16 passed (16)
```

### B2 — `render.mutate` had no error handling (Minor, folded in)

**File:** `web/src/features/inbox/Composer.tsx`

Two related gaps: (1) no `onError` on the quick-reply render mutation, so a failed render left the raw `/shortcut` text sitting in the box with no feedback, sendable verbatim on the next Ctrl+Enter; (2) `submit()` didn't check `render.isPending`, so a fast Ctrl+Enter could race ahead of an in-flight render and send the raw shortcut before it resolved.

**Fix:**
- `submit()` now also blocks while `render.isPending`.
- `render.mutate`'s `onError` clears the box (`setBody('')`) rather than leaving the raw shortcut, and a new `render.error` alert (styled like the existing `send.error` one) surfaces the failure.

**Covering tests**, both added to `Composer.test.tsx`:
- `clears the raw shortcut and surfaces the error when rendering a quick reply fails` — mocks the render POST to 500, asserts a `role="alert"` with the server message appears, the box empties, and a subsequent Ctrl+Enter fires no `/messages` POST.
- `does not send while a quick-reply render is still in flight` — holds the render POST's promise open (manual `resolve` captured), presses Ctrl+Enter while it's pending, and asserts no `/messages` POST fired; then resolves the render and confirms the interpolated body lands normally afterward.

**RED (before the fix — verified by temporarily reverting `Composer.tsx` via `git stash` and rerunning against the unmodified code, then restoring with `git stash pop`; `git diff` after the pop confirmed a byte-identical restore):**
```
npx vitest run src/features/inbox/Composer.test.tsx -t "render"
```
```
× Composer > clears the raw shortcut and surfaces the error when rendering a quick reply fails
  (timed out waiting for `findByRole('alert')` — no error ever surfaces)

× Composer > does not send while a quick-reply render is still in flight
  → expected true to be false // Object.is equality
```
The second failure is the sharpest evidence: with the guard removed, a real `POST .../messages` fired carrying the raw `/wifi` shortcut while the render call was still pending — exactly the "wrong message in front of a real person" risk the review named.

**GREEN (after restoring the fix):**
```
npx vitest run src/features/inbox/Composer.test.tsx
```
```
✓ src/features/inbox/Composer.test.tsx (19 tests)
Test Files  1 passed (1)
     Tests  19 passed (19)
```

### A1 — three/two/one-column layout (Important)

**File:** `web/src/features/inbox/GuestPanel.tsx`

`GuestPanel`'s `<aside>` was unconditionally `w-[300px] flex-none`, so the guest panel was jammed beside the thread even in InboxPage's existing mobile (`<768px`) single-column state. Changed to `hidden w-[300px] flex-none ... lg:block` — genuinely absent below `lg` (1024px), not zero-width (a `w-0 flex-none` element would still contribute its border). `InboxPage.tsx` already had the correct `md:` breakpoint logic collapsing list/thread to one pane below 768px (Task 12's work); this change was the only piece missing to get the full three/two/one states, since the `lg` cut now sits strictly inside the existing `md` cut.

No test file needed updating: `GuestPanel.test.tsx` asserts on content, not the `<aside>`'s className, and all 8 of its tests still pass.

### A2 — back navigation in the single-column state (Important)

**File:** `web/src/features/inbox/ConversationHeader.tsx`

Added a `<Link to="/app/inbox">← Back</Link>` at the start of the header, classed `md:hidden` so it only renders below 768px (where the conversation list is hidden and otherwise unreachable except via the browser back button). Real link with visible text (not a bare glyph), so its accessible name is "← Back".

No `ConversationHeader.test.tsx` exists yet; verified via live resize (below) and via the existing `ConversationView.test.tsx` (5 tests, unaffected — none of them query `getByRole('link')` singularly, so the new link doesn't collide).

### A3 — RequireAuth regression test (Important)

**File (new):** `web/src/auth/RequireAuth.test.tsx`

Mounts `RequireAuth` under a minimal two-route tree (`/app` protected, `/login` public) with a valid session pre-seeded into the query cache (`sessionFixture` via `renderWithProviders`). The protected screen (`ExpiringScreen`) fires two independent `api()` calls in an effect — simulating two components each discovering the dead session at roughly the same time — both mocked to 401, with `/api/auth/me` also mocked to 401 (a truly-dead session). Asserts the app lands on `/login` (`findByText('Login Screen')`) and that `/api/auth/me` was called **exactly once**, proving the two near-simultaneous 401s coalesced into a single refetch rather than firing one each.

**GREEN (against the current, fixed `RequireAuth.tsx`):**
```
npx vitest run src/auth/RequireAuth.test.tsx
```
```
✓ src/auth/RequireAuth.test.tsx (1 test)
Test Files  1 passed (1)
     Tests  1 passed (1)
```

**Discrimination check — guard removed:** temporarily replaced the `useRef` guard with an unconditional `onUnauthorized(() => { void refetch() })` and reran the same test with an explicit timeout flag. **The command did not return within the tool's 120s window and had to be force-stopped as a background task.** This is itself the finding: without the guard, the two 401s each trigger their own `refetch()`, each of which 401s again via `/api/auth/me`, each re-invoking the same handler — an unbounded chain of promise-chained refetches that never lets the query settle into a stable `error` state. The test doesn't fail with a clean assertion mismatch in this case; it **hangs**, because `findByText('Login Screen', {...})`'s internal `waitFor` polling never gets a moment where the DOM has settled and `/api/auth/me` has stopped being called. This matches exactly the caveat the review flagged as an acceptable outcome ("if removing the guard makes the test hang rather than fail cleanly, say so").

Restored the guard immediately after (`git diff` on `RequireAuth.tsx` showed zero diff — byte-identical to the original, confirming a clean restore) and reran to confirm GREEN again (shown above).

### A4 — order test can't catch a descending sort (Minor, folded in)

**File:** `web/src/features/inbox/ConversationList.test.tsx`

The old fixtures (`412` at `18:41`, `118` at `17:00`, expected order `['412','118']`) had `lastGuestMessageAt` monotonically decreasing in the same order as the expected rows — a bug that added a client-side sort by that field, descending, would have reproduced the same expected order and passed undetected.

Replaced with three fixtures (`205`/`412`/`118`, expected order `['205','412','118']`) chosen so that no single-field sort — ascending or descending — on any field `ConversationSummary` carries reproduces that order. Checked explicitly, field by field:

| field | values in server order | ascending sort order | descending sort order | matches expected (`205,412,118`)? |
|---|---|---|---|---|
| `id` | c-2, c-1, c-3 | c-1, c-2, c-3 | c-3, c-2, c-1 | no (neither direction) |
| `roomNumber` (string) | 205, 412, 118 | 118, 205, 412 | 412, 205, 118 | no |
| `lastGuestMessageAt` | 17:30, 18:41, 17:00 | 17:00, 17:30, 18:41 | 18:41, 17:30, 17:00 | no |
| `slaDueAt` | 17:45, 18:56, 16:30 | 16:30, 17:45, 18:56 | 18:56, 17:45, 16:30 | no |
| `openWorkOrderCount` | 1, 0, 2 | 0, 1, 2 | 2, 1, 0 | no |
| `assignedUserId` (has a null) | u-b, null, u-a | not a clean total order (null) | not a clean total order (null) | ruled out — no single well-defined order either way |
| guest name (first+last) | Nora Diaz, Sarah Chen, Milo Ahn | Milo Ahn, Nora Diaz, Sarah Chen | Sarah Chen, Nora Diaz, Milo Ahn | no |
| `channelPrimary`, `status`, `lastStaffMessageAt` | constant across all three (`sms`/`open`/`null`) | n/a — no ordering info | n/a | can't determine any order, so can't accidentally match |

Every field with three distinct values fails to reproduce the target order in either direction; the fields with ties or nulls (`assignedUserId`, the constant ones) can't produce a unique 3-item order at all, so they can't accidentally "get lucky" either.

**Verification:** `npx vitest run src/features/inbox/ConversationList.test.tsx` → 11/11 pass, including this test with the new fixtures.

### Covering-test and full-suite runs

```
npx vitest run src/features/inbox src/auth
```
```
Test Files  15 passed (15)
     Tests  116 passed (116)
```

```
npm test
```
```
Test Files  31 passed (31)
     Tests  250 passed (250)
```

```
npx tsc -b
```
Clean, no output, exit 0.

### Responsive verification — performed live, not just reasoned about

Dev server was already running (`server/dev_start.py` + `npm run dev`, both from a prior session). Used Playwright to navigate to a real conversation (`/app/inbox/e8eb...`, Sarah Chen / room 412) and resized the actual browser viewport, reading computed `display` off the real DOM at each width (not just reading the Tailwind classes):

- **1200px:** list, thread, and `<aside>` (guest panel) all `display !== 'none'` — three columns. Back link `display === 'none'`.
- **900px:** list and thread visible; `<aside>` `display === 'none'` — two columns. Back link still hidden (redundant — list is visible).
- **500px:** list hidden; thread visible; `<aside>` hidden; back link visible with accessible name "← Back" — one column, back nav present exactly where required.
- Clicked the "← Back" link at 500px: URL changed to `/app/inbox` and the conversation list became visible again (`offsetParent !== null`), confirming it's a real, working navigation, not just a rendered label.

This was an actual resize-and-inspect pass against the running app, not a static read of the CSS classes.

### Files changed (this fix round)

- `web/src/features/inbox/QuickReplyPalette.tsx` (B1 fix)
- `web/src/features/inbox/QuickReplyPalette.test.tsx` (B1 test)
- `web/src/features/inbox/Composer.tsx` (B2 fix)
- `web/src/features/inbox/Composer.test.tsx` (B2 tests)
- `web/src/features/inbox/GuestPanel.tsx` (A1 fix)
- `web/src/features/inbox/ConversationHeader.tsx` (A2 fix)
- `web/src/auth/RequireAuth.test.tsx` (A3 test, new file — `RequireAuth.tsx` itself unchanged)
- `web/src/features/inbox/ConversationList.test.tsx` (A4 fixture rewrite)

Task 15's files (`ConversationActions.tsx`, `DraftPromptBanner.tsx`, `CreateWorkOrderModal.tsx`, `ArchiveDialog.tsx`) were left untouched — none of the six items required changing them. `ConversationHeader.tsx` (touched for A2) does render Task 15's `ConversationActions`, but only as an existing, unmodified child; nothing about that component changed.

### Concerns

None blocking. Note for whoever picks this up next: A3's discrimination check demonstrated that removing the guard produces a **hang**, not a clean test failure — if CI ever needs to catch a regression here automatically (rather than a human noticing a stuck test run), this test would need an explicit `timeout` short enough to fail loudly within CI's own limits rather than exhausting whatever global timeout is configured. I did not add one since the current default let the fault show clearly enough during manual verification, and the guard itself is what's actually shipped and tested green.
