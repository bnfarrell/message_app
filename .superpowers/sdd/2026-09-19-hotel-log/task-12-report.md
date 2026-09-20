# Task 12 report: LogEntryCard and AckBar

## What I implemented

- `web/src/features/log/AckBar.tsx` — `AckBar({ entry })`. Returns `null` when
  `entry.requiresAck` is false. Otherwise renders a `<progress>` element plus
  "N of M acknowledged" text (from `entry.acks?.length` and
  `entry.ackExpectedCount`), then one of: "You acknowledged this" (when
  `ackedByMe`), an "Acknowledge" button that calls `useAckLogEntry().mutate(entry.id)`
  (when `canAck`), or nothing (neither). Lists `entry.outstanding` names below
  when non-empty. Modelled the progress-row idiom on `web/src/features/board/`
  (no existing progress bar there, so used a plain `<progress>` + text row
  rather than inventing a bespoke visual — nothing more elaborate existed to
  match).

- `web/src/features/log/LogEntryCard.tsx` — `LogEntryCard({ entry })`. Header
  row modelled on `WorkOrderCard.tsx` (`Avatar` + name + `relativeTime` +
  `Badge` for shift/department, using `web/src/components/ui`'s `Avatar`,
  `Badge`, `Button`). Body is rendered by a local `renderBody()` that splits
  on `TOKEN_RE` via `body.matchAll(TOKEN_RE)` and maps each match to a
  `<span className="font-semibold text-accent">{match[1]}</span>` carrying
  the display name; no `dangerouslySetInnerHTML` anywhere. Footer: photo
  `<img>` when `photoUrl` set, links to `/app/work-orders/:id` /
  `/app/messages/:id` when linked (paths matched from `WorkOrderCard.tsx` /
  `NotificationsPage.tsx`), then `<AckBar entry={entry} />`. Pin control
  appears only when `can('pin_log_entry')`, calls
  `useSetLogPinned().mutate({ id, pinned: !entry.pinned })` (POST when pinning,
  DELETE when unpinning, per the hook's existing implementation), label flips
  Pin/Unpin off `entry.pinned`.

## Tests written

`AckBar.test.tsx` (6 tests): null when `requiresAck` false; "2 of 5
acknowledged" count; enabled Acknowledge button fires exactly one POST to
`/ack`; "You acknowledged this" + no button when `ackedByMe`; outstanding
names listed; no button when neither `canAck` nor `ackedByMe`.

`LogEntryCard.test.tsx` (9 tests): author/shift-badge("AM")/department tag;
mention renders as display name only with raw `@[...](user:...)` absent from
the DOM (`queryByText(/\]\(user:/)` null); **two entries with mentions
rendered in the same pass** (the required g-flag-specific test) — both
display names must appear and no raw token leaks; img present when
`photoUrl` set / absent when null (two separate tests); Pin hidden without
`pin_log_entry`; Pin button POSTs; Unpin button DELETEs; a mention whose
`displayName` is `<b>x</b>` renders as the literal string `<b>x</b>` with no
`<b>` element in the DOM.

All fixtures use 36-char UUID-shaped ids (`bbbbbbbb-bbbb-...`,
`cccccccc-cccc-...`) per the brief's hazard note, built via `tokenFor()` from
`MentionInput.tsx` rather than hand-formatted strings.

## TDD evidence

- `AckBar.tsx` and its test were written together (implementation is small
  and the file didn't exist yet — RED was "module not found" implicitly);
  ran `npx vitest run "src/features/log/AckBar.test.tsx"` → GREEN, 6/6 passed
  on first run.
- `LogEntryCard.test.tsx` was written and run *before* `LogEntryCard.tsx`
  existed:
  ```
  npx vitest run "src/features/log/LogEntryCard.test.tsx"
  → FAIL: Failed to resolve import "./LogEntryCard" ... Does the file exist?
  ```
  Then implemented `LogEntryCard.tsx`; re-ran:
  ```
  npx vitest run "src/features/log/LogEntryCard.test.tsx"
  → 9 tests passed
  ```

## Sabotage verification

1. **XSS-safe rendering.** Replaced the body `<p>` with
   `dangerouslySetInnerHTML={{ __html: entry.body.replace(TOKEN_RE, '$1') }}`.
   Re-ran the suite: 3 failed, including the HTML-display-name test — the DOM
   showed a literal `<b>x</b>` element instead of the text `<b>x</b>`
   (`expect(document.querySelector('b')).toBeNull()` failed, and
   `getByText('<b>x</b>')` also failed since the text was split by the real
   `<b>` tag). Reverted to `renderBody(entry.body)`; re-ran → 9/9 passed.

2. **Capability gate on Pin.** Changed `can('pin_log_entry') ?` to `true ?`.
   Re-ran: "shows no Pin control without the pin_log_entry capability" failed
   — an unwanted `<button>Pin</button>` was found for the `'agent'` role.
   Reverted; re-ran → 9/9 passed.

3. **g-flag-safe parsing.** Replaced the `matchAll` loop with a single
   `TOKEN_RE.exec(body)` call (the realistic misuse pattern: one exec per
   render rather than draining the iterator, which is exactly what would
   happen if a developer wrote `if (TOKEN_RE.test(...))` or a one-shot
   `.exec()` per entry against the shared instance). Re-ran: the
   two-entries-in-one-pass test failed — entry 1's "Ana Marquez" mention did
   not render (its raw token was left as literal text, matching the brief's
   predicted symptom), while entry 2's "Priya Shah" rendered fine, because
   `TOKEN_RE.lastIndex` carried over from entry 1's exec call into entry 2's
   call, then reset to 0 only after entry 2's failed match — masking the
   defect on the very next call. Reverted to the `matchAll` loop; re-ran →
   9/9 passed.

Also ran a targeted sabotage on `AckBar`'s server-trust rule: changed
`entry.canAck` to `true` in the button-gating ternary. "shows no Acknowledge
button when the viewer was never asked" failed as expected (an unwanted
button appeared). Reverted; re-ran → 6/6 passed.

## Files changed

- `web/src/features/log/AckBar.tsx` (new)
- `web/src/features/log/AckBar.test.tsx` (new)
- `web/src/features/log/LogEntryCard.tsx` (new)
- `web/src/features/log/LogEntryCard.test.tsx` (new)

Commit: `b106c44 feat(web): hotel log entry card and acknowledgement bar`

## Verification run

- `cd web && npm test` → 64 files, **632 passed** (baseline 617 + 15 new: 6
  AckBar + 9 LogEntryCard). No other file's test count changed.
- `cd web && npm run lint` → clean, no output.
- `cd web && npm run build` → `tsc -b && vite build` clean, 165 modules
  transformed, no errors.

## Self-review findings

- `renderBody` keys spans with a simple incrementing counter scoped to a
  single call — safe since it's local to one `entry.body` parse and each
  `LogEntryCard` instance has its own closure invocation.
- Considered whether `AckBar`'s outstanding-list should be gated to only
  render for people who can see it (e.g. hide names from other guests) —
  brief and server contract (`can_ack`/`outstanding` computed server-side)
  give no signal that client-side gating is needed here, so I did not add
  any hiding logic beyond what the server sends.
- Did not add an `aria-label` to the `<progress>` element; the adjacent text
  span already states the same information ("N of M acknowledged"), so a
  screen reader gets it from the text without a redundant label. Left as-is
  per "no speculative additions."
- The Pin/Unpin button reuses `Button`'s `ghost` variant like other
  low-emphasis header controls elsewhere in the codebase (no direct existing
  Pin control to model against; kept it visually secondary next to the
  primary content).
- Did not touch `server/app/domain/users.py`, `server/data/app.db*`, or
  `two.png`/`.claude/`/`images/` — all pre-existing, out of scope, left
  alone.

## Concerns

None blocking. Two minor judgment calls worth flagging to the reviewer:

1. The brief's footer spec ("links to a work order or conversation when
   present") wasn't covered by an explicit test bullet, so I implemented it
   minimally (plain `<Link>`s, no icons/styling beyond matching the accent
   text style used elsewhere) without a dedicated test. If a downstream task
   expects a specific link label/format, it isn't locked down by a test yet.
2. `AckBar`'s progress bar visual is a plain native `<progress>` element
   rather than a Tailwind-styled bar, since `web/src/features/board/` had no
   existing progress-indicator component to match against — I judged this
   simplest and least likely to need bespoke CSS, but flagging in case the
   team has a preferred pattern elsewhere I didn't find.
