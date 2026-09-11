# Task 13 report: Conversation thread, notes, guest panel

## What I implemented

Exactly the brief's file list, in order:

- `web/src/api/hooks/conversations.ts` — added `useAddNote(conversationId)` (`POST conversations/<id>/notes`, invalidates the detail) and `usePatchConversation(conversationId)` (`PATCH conversations/<id>`, invalidates the detail and every list), verbatim from Step 1.
- `web/src/features/inbox/MessageBubble.tsx` — renders one message: inbound left (`bg-surface2`/`border-border2`/`text-text`), outbound right (`bg-outBg`/`text-outText`), automated left with `Automatic` label (`bg-autoBg`/`text-autoText`/`border-autoBorder`), redaction chip (`Badge tone="warn"`, "Card number redacted"), delivery-status copy (`Sending…`/`Sent`/`Delivered`/`Failed`), failed state in `text-dangerText` with the provider error code and a Retry button. Max width 470px, `rounded-card`, 12/14px padding, 14.5px text — all per the mockup's `.bubble`.
- `web/src/features/inbox/GuestPanel.tsx` — the six §5.2 sections in order: Guest, Stay, Consent, Work orders, Prompts, Notes. Handles a guest with no stay ("No stay on file").
- `web/src/features/inbox/ConversationHeader.tsx` — room number, guest name, channel/tier/stay-count chips, presence badge, opted-out chip, `SlaChip`. Exports `presenceLine` for its own unit test, excluding the current user from the presence line.
- `web/src/features/inbox/ConversationView.tsx` — replaces Task 12's stub wholesale. Merges `messages` and `notes` into one timeline sorted by `sentAt ?? '9999'` (queued sorts last) / `createdAt`, renders `MessageBubble` or an inline "Internal" note block, reports presence via `setPresence` on mount/unmount, renders `ConversationHeader` + `GuestPanel`. Composer slot left as a comment for Task 14; no `ConversationActions` (Task 15).

## What I tested and the results

All four test files from the brief, written verbatim except for the fixes described below (Step 2), confirmed to fail first (Step 3), then implementation written (Steps 4-6), then confirmed green (Step 7).

**Final full suite:**
```
cd web && npm test
```
```
Test Files  24 passed (24)
     Tests  190 passed (190)
```
No `act()` warnings, no unhandled rejections, no React Router future-flag warnings — I grepped the full run output for "warning"/"act("/"unhandled"/"future flag" and got zero hits.

Target-suite breakdown (all passing): `MessageBubble.test.tsx` 8, `ConversationView.test.tsx` 5, `presenceLine.test.ts` 5, `GuestPanel.test.tsx` 8 — matches the brief's expected counts exactly.

## TDD evidence

**RED** — `cd web && npx vitest run src/features/inbox` (after writing all four test files against the still-stub `ConversationView.tsx` and nonexistent `MessageBubble`/`GuestPanel`/`ConversationHeader`):
```
Test Files  4 failed | 2 passed (6)
     Tests  5 failed | 17 passed (22)
```
`MessageBubble.test.tsx` and `GuestPanel.test.tsx` failed at import resolution (modules didn't exist); `presenceLine.test.ts` failed because `ConversationHeader` didn't export `presenceLine`; `ConversationView.test.tsx`'s 5 tests failed because the stub only ever renders the guest's name, never room number, chips, notes, or an error state — e.g. `findByText('Conversation not found')` timed out against `<div class="p-4 text-sm font-semibold" />`. This is the expected failure shape: missing modules plus a stub that doesn't implement any of the tested behavior.

**GREEN** — `cd web && npm test`:
```
Test Files  24 passed (24)
     Tests  190 passed (190)
```

## Defects found in the brief's literal code (fixed, not worked around)

Per the task's instruction to report rather than bend correct code to fit a broken test, I found and fixed four scaffolding/test defects. None required changing the prescribed component behavior.

1. **`GuestPanel.test.tsx` imports `aStay` but never uses it.** With `noUnusedLocals: true` (project-wide `tsconfig.json`, no per-file override, `include: ["src", ...]` so test files are checked too), this fails `tsc -b`. Fix: dropped `aStay` from the import list.

2. **The brief's `GuestPanel.tsx` uses `React.ReactNode` as a bare type without importing `React`.** No file in this codebase relies on the UMD-global `React` namespace (`allowUmdGlobalAccess` isn't set), and every existing component (e.g. `EmptyState.tsx`) imports `type { ReactNode } from 'react'` instead. `React.ReactNode` would fail to compile ("Cannot find namespace 'React'"). Fix: `import type { ReactNode } from 'react'`, used bare as the codebase already does elsewhere.

3. **The brief's `ConversationView.test.tsx` fake `WebSocket` class omits `static OPEN = 1`.** Production code in `web/src/api/ws.ts` (Task 11, already committed, not part of this task) does:
   ```ts
   if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(...)
   ```
   With no static `OPEN` on the stubbed global, `WebSocket.OPEN` is `undefined`. Because `ConversationView`'s presence effect fires *before* `RealtimeProvider`'s own `connect()` effect (child effects fire before parent effects in React), `socket.current` is still `null` at that moment, so `socket.current?.readyState` is also `undefined`. `undefined === undefined` is `true`, so the guard incorrectly passes and `socket.current.send(...)` throws on the null ref. The existing `web/src/api/ws.test.tsx` (Task 11, 23 passing tests) uses the identical fake-socket pattern but *does* define `static OPEN = 1` — proving this is missing test scaffolding, not a production bug (real browsers always define `WebSocket.OPEN`). Fix: added `static OPEN = 1` to the fake class in the brief's `ConversationView.test.tsx`, matching the established precedent.

4. **Two `ConversationView.test.tsx` assertions can't hold against the brief's own prescribed implementation.** The brief's own `ConversationHeader.tsx` (Step 6) and `GuestPanel.tsx` (Step 5) code — both given verbatim in the same brief — legitimately render the guest's name in *both* the header and the guest panel (§5.2 requires the panel to show it; §5.3 requires the header to show it), and both legitimately render an "Opted out" indicator in both places when the guest is opted out. The literal test code used unscoped `screen.getByText('Sarah Chen')` / `screen.findByText(/opted out/i)`, which throw "Found multiple elements" once both components render together inside `ConversationView` — this is not a flaw in the implementation, it's the test failing to scope its query to the region it claims to test ("renders the room, guest and stay chips **in the header**"). Fix: scoped the header test to `within(screen.getByRole('banner'))`, and changed the opted-out test to `findAllByText` + `length > 0`, since either surface displaying the warning satisfies the test's own intent ("warns... does not disable the thread").

I verified all four fixes by confirming the tests actually reproduce the original failure (RED) before the fix and pass (GREEN) after — none of these were guessed.

## Live verification

Started the real backend (`.venv/Scripts/python.exe server/dev_start.py`, port 5000) and the Vite dev server (`npm run dev`, port 5175 — 5173/5174 occupied by leftover processes from earlier task sessions), then drove the browser via Playwright, logged out of the stale Eli session and signed in fresh as `ava@hvh.test` / `Password123!`.

**Room 412, Sarah Chen** (`e8eb4142-c857-4550-ad75-41fa7ab0a82a` — the two-notes conversation, matching the brief's Step 8 target):
- Guest's inbound messages render left in the plain surface treatment; Ava's outbound reply renders right in the dark `outBg` treatment, labelled "Ava", "Delivered".
- The automated welcome message renders left, bordered, labelled "Automatic".
- Both internal notes render in the amber note treatment, each labelled "Internal" with the "●" marker, author name, and clock time, correctly interleaved **after** the last message by timestamp (notes were created chronologically last in this seed).
- Guest panel: Guest (name, mono phone, GOLD badge), Stay (412 · Accessible King, dates, party, "2th stay", status), Consent ("Opted in", green), Work orders ("None" — this conversation has none), Prompts ("None pending"), Notes (both note bodies listed) — all six sections present in §5.2 order.

**Room 403, Dmitri Rahman** (`08332007-d269-4e08-b1d3-2eee92b58a95`, has a linked work order): confirmed the panel's Work orders section renders a real link — `<a href="/app/work-orders/54293293-50cc-429c-8115-ca12a7497c49">Late checkout request — 2 PM</a>` with an "assigned" status badge.

**Redacted-card message — found live, contrary to the task's stated assumption.** The task brief said "I queried the database directly: opted_out=0 ... so those two treatments cannot be seen live." I queried the seeded SQLite DB myself before verifying and found `redacted=1` on message `8c02153e-8371-41aa-b4cd-4b3fcb936b61` (conversation `b19a01c8-f1ff-4b45-93bb-c7e00176fcfc`, room 102, Dmitri Costa) with body `"you can charge it to **** **** **** 4242"`. Opened it live: the message body renders exactly as stored (`**** **** **** 4242`) with an amber `Card number redacted` chip underneath, in the `Badge tone="warn"` treatment — confirmed both in the accessibility snapshot and a full-page screenshot. **This treatment was verified live, not just by unit test**, correcting the task's stated limitation.

**Could not verify live, and why:**
- **Opted-out guest chip.** I found one opted-out guest in the seed (`sms_consent_status='opted_out'`, id `6b8a1dcc-...`), but queried and confirmed they have **no conversation row at all** (`select id from conversation where guest_id=...` → empty), so there is no thread to open. The task's assumption holds for this specific treatment: it genuinely cannot be reached live. Covered by unit tests (`ConversationView.test.tsx`'s "warns but does not disable the thread for an opted-out guest" and `GuestPanel.test.tsx`'s "shows consent status as a red chip when opted out").
- **Cross-session presence** (`marcus@hvh.test` in a second profile, both headers naming each other within seconds). The Playwright MCP tool I have access to drives a single browser context with one shared cookie jar — logging in as a second user in a second tab evicts the first session's auth cookie rather than creating a genuinely concurrent second session, so I could not observe two simultaneous presence updates. I did not fake or approximate this. The underlying logic is covered by unit tests instead: all 5 `presenceLine` copy tests pass (including the exclusion of the current user and the "and N others" pluralization), and the pre-existing `web/src/api/ws.test.tsx` (23 tests, unmodified by this task) covers the `presence.update` socket-message handling that `ConversationHeader` consumes.

## `npx tsc -b`

Clean, zero output, confirmed with `npx tsc -b --force` after all fixes above (exit code 0).

## Files changed

- `web/src/api/hooks/conversations.ts` (modified — added `useAddNote`, `usePatchConversation`)
- `web/src/features/inbox/ConversationView.tsx` (replaced Task 12's stub)
- `web/src/features/inbox/MessageBubble.tsx` (new)
- `web/src/features/inbox/MessageBubble.test.tsx` (new)
- `web/src/features/inbox/GuestPanel.tsx` (new)
- `web/src/features/inbox/GuestPanel.test.tsx` (new, minus the unused `aStay` import — defect #1 above)
- `web/src/features/inbox/ConversationHeader.tsx` (new)
- `web/src/features/inbox/ConversationView.test.tsx` (new, with the `static OPEN = 1` and `within(header)`/`findAllByText` fixes — defects #3 and #4 above)
- `web/src/features/inbox/presenceLine.test.ts` (new, verbatim)

Commit: `c3380f0` — "feat(web): conversation thread with interleaved notes, guest panel and presence"

## Self-review

- **Completeness:** all 8 bubble / 5 view / 5 presence-copy / 8 panel tests pass (190/190 total suite).
- **Quality:** timeline interleaves correctly by `sentAt`/`createdAt`, queued (`sentAt: null`) messages sort last via the `'9999'` sentinel; a note is unmistakably distinct (`bg-noteBg`/`border-noteBorder`/`text-noteText`, "Internal" label, `text-noteIcon` marker) both in unit tests and live; the redaction chip renders and was verified live; `presenceLine` excludes the current user (`others = presence[id].filter(u => u.id !== user.id)`) and pluralizes per the five unit tests; the guest panel renders "No stay on file" without crashing when `stay: null`.
- **Discipline:** no composer built (comment left at the mount point for Task 14); no `ConversationActions` (assign/snooze/archive/create-work-order — Task 15's job); `ConversationHeader`'s action area is simply not present, nothing stubbed for it beyond what the brief's own header code already includes (presence badge, opted-out chip, SLA chip).
- **Testing:** all four test files exercise real rendered output (DOM text/class assertions, not mocked internals) against a real `QueryClientProvider` + `MemoryRouter` + `SessionProvider`/`RealtimeProvider` stack, matching the project's existing harness conventions. Output is pristine.

## Issues or concerns

- The four defects above (one unused-import, one missing-namespace-import, one missing-static-constant, two over-tight assertions) are all fixed and documented; I did not alter any prescribed component behavior to satisfy them.
- The task's own stated seed-data limitation ("no redacted-card message") did not hold — the redaction treatment **was** verifiable live and I did so. I flag this only so the assumption isn't propagated into later tasks' verification steps.
- Presence cross-session verification remains unit-test-only, for the tooling reason given above, not a shortcut taken.
- Dev server processes (backend on 5000, Vite on 5175) were left running for continuity with other in-flight task sessions that already had similar processes running before I started; I did not kill any pre-existing process.
