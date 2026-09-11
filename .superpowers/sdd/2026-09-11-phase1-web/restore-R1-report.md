# Restoration R1 — report

Status: **DONE_WITH_CONCERNS** (the concerns are findings, not defects in the delivered work).

Commits on `main`, one per item:

| sha | item |
| --- | --- |
| `9e0b37f` | R1.1 internal-note composer |
| `e15daf4` | R1.2 guest panel "Previous stays" |
| `28e8b97` | R1.3 composer "Quick" and "Work order" buttons |

Verification of the final tree: **web 381 tests passing** (was 366; +15 new), `npx tsc -b` clean,
`npm run lint` exits 0 with no output, `npm run build` clean. No server files were touched, so the
server suite was not re-run. Working tree clean.

---

## R1.1 — Internal note composer

**What was built.** A segmented `Reply | Note` toggle directly above the composer input, exactly as
the brief specified. In Note mode the send action calls the existing `useAddNote`, the placeholder
becomes "Internal note — not sent to the guest", the send button reads "Add note", and the input is
tinted with the existing `--noteBg` / `--noteBorder` / `--noteText` tokens so it matches the note
blocks already rendered in the thread. Ctrl+Enter submits in both modes. A rejected note gives the
text back, mirroring the existing behaviour for a rejected send.

**Files.**
- `web/src/features/inbox/Composer.tsx` — the toggle, note mode, and mode-dependent submit.
- `web/src/features/inbox/Composer.test.tsx` — 7 new tests.
- `web/src/features/inbox/ConversationView.test.tsx` — 1 new test covering the whole loop.

**Hook / endpoint.** `useAddNote` (`web/src/api/hooks/conversations.ts:54`), unchanged; it already
invalidates `qk.conversation`, which is what puts the new note into the thread. It posts to
`POST /api/p/<pid>/conversations/<id>/notes`, gated server-side on `add_note`. This is the hook's
first call site. No new hook was written and none was needed.

**Capability gating.** The toggle is gated on `can('add_note')`, **not** on `reply`. The early
return that previously read `if (!can('reply')) return null` now reads
`if (!canReply && !canNote) return null`, so a role with `add_note` alone gets a working composer.
The `Reply` segment itself is gated on `can('reply')`, so corporate sees a single `NOTE` pill that
labels the mode and is never offered Reply. The initial mode is `canReply ? 'reply' : 'note'`.
No role in the matrix has `reply` without `add_note` (`add_note` is the full `STAFF` list), so the
converse case is unreachable and is not tested.

**Note mode drops what does not apply.** No segment counter, no quick-reply palette (the palette's
open condition now requires `mode === 'reply'`), no asset picker, and — per R1.3 — no Quick or
Work order button. The opted-out SMS warning is also suppressed in Note mode: its text is
"A send will be rejected unless they text START", which is false of a note. The header's own
"Opted out" badge still shows the consent state.

**Opted-out path.** Note mode stays fully usable for an opted-out guest; this is covered by a test
that posts a note with `smsConsentStatus: 'opted_out'` and asserts the POST body. Nothing in the
note path consults consent, client-side or server-side.

**Exercised against the running server** (API on 127.0.0.1:5200, web on 5173, seeded dev DB):
- `POST /conversations/<id>/notes` as `ava@hvh.test` → **201**, and the note is present in the
  conversation detail payload on the next read.
- Spec §6's audit row: `select action, entity_type from audit_log where action like 'note%'` →
  `('note.created', 'internal_note', ...)`. Before this work that query returned **zero rows**;
  the seed's own internal notes carry no audit rows because they are inserted directly. The row is
  now reachable from the product, confirmed three times (one API call, one as corporate, one
  written through the UI composer in the browser).
- `casey@group.test` (corporate): `POST .../notes` → **201**; `POST .../messages` → **403**. The
  UI gating therefore matches the server exactly.
- In the browser as corporate: the thread renders with a `NOTE`-only toggle, a tinted textarea, an
  "Add note" button, no Assign/Snooze/Create-work-order/Archive in the header, and typing + clicking
  Add note produced a real note and a real `note.created` audit row. Corporate now has a usable
  action in the inbox for the first time.
- Both themes checked visually in the browser. See the token-conflict finding below.

## R1.2 — Guest panel "Previous stays"

**What was built.** A `Previous stays` section at the foot of `GuestPanel`, following the file's
existing `Section` pattern, rendering one mono line per past stay and "None" for a first-time guest.

**Files.**
- `web/src/features/inbox/GuestPanel.tsx`
- `web/src/features/inbox/GuestPanel.test.tsx` — 4 new tests; the file also gained a `fetch` stub,
  which it previously did without because the panel made no requests.

**Hook / endpoint.** `useGuest` (`web/src/api/hooks/users.ts:25`) → `GET /api/p/<pid>/guests/<id>`.
First call site; no new hook.

**What is rendered, and what is not.** `StayOut` carries `id, roomNumber?, roomType?, status,
arrivalDate, departureDate, adults, children, stayCount, isReturnGuest`. It has **no rating field
and no conversation count**, so the mockup's `1 conv` and `5★` are not rendered — the brief
anticipated this and told me to render only real fields. Each line is
`MONTH YEAR · <n>N · <STATUS>`, e.g. `JUN 2026 · 2N · CHECKED OUT`. Nights are computed from the two
date-only strings via `Date.UTC`, deliberately not `new Date(str)`, so a local timezone cannot shift
the count. The current stay is excluded by `id`.

**Capability gating — a decision the brief did not cover.** `GET /guests/<id>` is gated server-side
on `view_all_conversations` (`server/app/api/guests.py:18`, with a docstring explaining that the
payload is strictly more than dept_staff may read). `dept_staff` lacks that capability. Rendering
the section unconditionally would have fired a request that can only 403 for every dept_staff user
opening any conversation. So the section **and** its query are gated on
`can('view_all_conversations')`; `useGuest` is passed `undefined` for those roles, which leaves its
`enabled` false and issues no request. Verified live: `eli@hvh.test` (dept_staff) gets **403** from
that endpoint; `ava@hvh.test` (agent) gets **200**. A test asserts both the hidden section and the
absent request.

**Seed reality.** The dev seed has **106 guests and 106 stay rows, with no guest holding more than
one** (`select guest_id, count(*) from stay group by guest_id having count(*) > 1` returns nothing).
So against current seed data this section always renders "None", including for guests whose `Stay.
stayCount` says "4th stay" — that column is denormalised and has no sibling rows behind it. The
feature is correct and is covered by tests with multi-stay fixtures, but it cannot be demonstrated
by clicking around the seeded app. Flagged rather than worked around.

## R1.3 — Composer "Quick" and "Work order" buttons

**What was built.** `Quick · Asset · Work order` in that order in the composer action row, matching
the mockup's ordering. Quick opens the existing `QuickReplyPalette`; Work order opens the existing
`CreateWorkOrderModal`. The header's "Create work order" action was left exactly where it was.

**Files.** `web/src/features/inbox/Composer.tsx`, `web/src/features/inbox/Composer.test.tsx`
(4 new tests).

**Reuse.** No second palette and no second modal component. Quick sets a `paletteForced` flag that
feeds the same `paletteOpen` expression the `/` prefix feeds, and shares the same
`paletteDismissed` close state. One deliberate refinement: when the palette is forced open over a
draft that is not a `/`-shortcut, the term passed to `QuickReplyPalette` is `''` rather than the
draft text. Passing the draft would filter the list by prose that was never a shortcut, so the
palette would usually match nothing and render `null` — the button would appear to do nothing.
Forcing the draft to `/` instead would destroy what the agent had typed. Listing everything is the
only option that neither silently fails nor eats the draft; a test asserts the draft survives.

**Capability gating.** Quick and Asset are inside the `!noteMode` branch, which is itself inside a
composer that only renders its reply affordances for a role with `reply`; Work order additionally
requires `can('create_work_order')`. Note that with the current matrix every role holding `reply`
also holds `create_work_order`, so the Work-order gate has no reachable negative case today and is
not tested — it is there because the matrix is data and may change.

**One structural change.** `CreateWorkOrderModal` calls `useToast` unconditionally, so mounting it
always (as `ConversationActions` does) would force every consumer of `Composer` to provide a
`ToastProvider`. It is mounted only while open instead. This also avoids a second idle
`useWorkOrderPrefill` query instance per conversation.

---

## Found but not fixed

1. **`cn` does not resolve Tailwind conflicts, and this is a live trap for the palette discipline.**
   `web/src/lib/cn.ts` is a plain `join(' ')`; there is no `tailwind-merge`. My first note-mode
   tint (`className="border-noteBorder bg-noteBg text-noteText"` on `Textarea`) produced the correct
   border but **kept `bg-surface2` and `text-text`** — verified in the browser with
   `getComputedStyle`: background `rgb(238,242,247)` (`--surface2`), not `#fff8e1` (`--noteBg`).
   The winner is decided by CSS source order, which follows the token array order in
   `tailwind.config.js`, not by the order of the class string. I fixed my own case with Tailwind's
   important modifier (`!bg-noteBg`), the first use of that modifier in the codebase. The general
   hazard remains: any component that accepts a `className` override of a colour already set in its
   base classes can silently ignore it, and it will not show up in tests, tsc, or lint — only in a
   browser. Worth either adopting `tailwind-merge` in `cn` or writing this down somewhere the next
   implementer will see it. I did not change `cn`; that is far outside R1.

2. **Brief anchor drift (all minor, all verified before editing).**
   - `server/app/api/conversations.py:78-88` → the `add_note` route is actually **79-90**.
   - `Main.dc.html:218-221` → the `Previous stays` heading is on **219** (218 is the wrapper div).
   - `Main.dc.html:144-146`, `Main.dc.html:165-167`, `server/app/schemas/users.py:52-55`,
     `web/src/api/hooks/conversations.ts` / `users.ts` — all exact.
   - The brief is correct that capabilities live in `web/src/auth/capabilities.ts`; my dispatch note
     said `web/src/lib/capabilities.ts`, which does not exist.

3. **A pre-existing test assertion was superseded, not broken.** `Composer.test.tsx`'s
   "renders nothing for a role without the reply capability" (added in Task 14) encoded the exact
   behaviour R1.1 exists to undo. I replaced it with a test asserting the intended new contract —
   corporate gets a note composer and still no outbound send — and said so in the test comment and
   the commit message. Nothing else in the suite depended on it.

4. **The `AssetPicker` trigger is labelled "Attach", not "Asset".** The mockup's middle button says
   Asset. Renaming it is a one-word change but it is outside R1's scope and would churn an existing
   test; the brief only asked for ordering and for the two missing buttons. Left alone.

5. **Composer action buttons use the `default` Button variant, not `ghost`.** The mockup draws all
   three as ghost buttons, but `AssetPicker` is a `Dropdown` whose trigger is a fixed bordered
   button, and a borderless Quick beside a bordered Attach beside a borderless Work order looks
   wrong in the running app. Making all three bordered matches both `ConversationActions` and the
   adjacent Attach control. If exact mockup fidelity is wanted here, the fix belongs in `Dropdown`,
   not in `Composer`.

6. **Presence still reports `composing` while an internal note is being typed**, so other viewers
   see "X is replying" when X is writing a note nobody outside the hotel will read. Changing it
   means either a new presence state on the wire or suppressing presence in note mode; both are
   server-visible decisions and neither was in scope. Left as-is deliberately.

7. **Three verification notes remain in the dev database** (`server/data/app.db`): two on
   conversation `40378618…` from the API checks and one written through the UI as corporate, plus
   their three `note.created` audit rows. They are the evidence for the §6 claim above, so I left
   them rather than deleting audit history; a re-seed clears them.

8. **`score.png` was sitting untracked at the repo root** when I started and nothing in the repo
   references it. I did not create it and did not delete it. Not mine to judge, but it should
   probably not be there.

---

# Fix round 1

Commit: **`8094d4f`** — `fix(web): four review findings on restoration R1`, on top of `554a950`.
All four findings accepted; none re-litigated. One of them turned out to have a second half the
review did not name, described under F1.

## F1 — the forced palette was never released

**Accepted, and the finding understated the blast radius.** `paletteForced` had no release at all:
the `/` path is released by `slashOpen` going false on the first space, and my flag had no
equivalent. Two fixes:

- `onChange` now clears `paletteForced`. A forced palette carries no term, so it never narrowed as
  you typed — releasing it on the first keystroke is the behaviour that matches what it can do.
- `submit()` clears it too, for the case the keystroke fix does not reach: a draft that arrived
  without typing (a prompt draft, or the short link `AssetPicker` appends via `setBody`), Quick
  clicked, then Ctrl+Enter.

**The half the review did not name.** While writing the second regression test I found that
Ctrl+Enter over an open palette fires *both* handlers: React's `onKeyDown` on the textarea sends,
then `QuickReplyPalette`'s document-level listener picks, and the render result lands in the box the
send has just emptied — a template nobody asked for, sitting where the agent expects an empty
composer. Clearing `paletteForced` inside `submit()` does not prevent this: the state flush has not
re-rendered by the time the document listener runs in the same event, and that listener closes over
the matches it already had.

I proved it before fixing it — the assertion `no POST to /render` failed on the then-current code:

```
× Composer > does not leave the forced palette open over the box after a send
Tests  1 failed | 32 skipped (33)
```

Fixed at the source in `web/src/features/inbox/QuickReplyPalette.tsx`: the Enter branch now returns
early when `ctrlKey || metaKey` is held. Ctrl+Enter means send and only send. This also covers the
pre-existing `/`-prefix version of the same collision, which was reachable before this wave.

## F2 — no focus indicator in Note mode

**Accepted.** `Textarea` pairs `focus:outline-none` with `focus:border-accent` as its only focus
affordance, and `!border-noteBorder` beats a non-important `focus:border-accent` outright. Took the
reviewer's first suggestion — `focus:!border-accent` — rather than reordering the token array,
because reordering fixes one pair of tokens by coincidence of position and would be silently undone
by the wave that is retuning the palette. Two important declarations resolve by specificity, and
`.focus\:\!border-accent:focus` (0,2,0) beats `.\!border-noteBorder` (0,1,0).

Verified live in the browser rather than argued from specificity, in both themes:

| theme | blurred border | focused border |
| --- | --- | --- |
| light | `rgb(230, 201, 106)` = `--noteBorder` | `rgb(37, 99, 235)` = `--accent` |
| dark | `rgb(90, 74, 18)` = `--noteBorder` | `rgb(79, 143, 212)` = `--accent` |

The reviewer's instruction to check other interactive elements I touched: the only other colour
overrides in this diff are on non-interactive elements (the `ModeTab` buttons set colours that have
no base-class counterpart on a bare `<button>`, and the stay lines are `<li>`s). `Textarea` is the
only place a base-class colour was being overridden, which matches what the reviewer found
independently.

## F3 — note submit left the asset and prompt armed

**Accepted, and "minor" undersells it.** This is the only finding in the round that corrupts stored
data rather than degrading an interaction: `digital_asset_id` on a message whose body never carried
that link makes asset-click attribution wrong in a way nothing downstream can detect. The note
branch now clears both, exactly as the reply branch does.

## F4 — a failed stay lookup read as "first-time guest"

**Accepted.** `guestDetail.error` is now consulted first and renders
`Stay history unavailable` in `--dangerText`. "None" and "we could not find out" were rendering
identically, and they are opposites.

## Not touched, as instructed

The active Reply tab's `bg-surface` inside a `bg-surface2` track — the selected-state inversion
between themes — is left alone for the palette-retuning wave.

## Verification

Files amended: `Composer.tsx`, `Composer.test.tsx`, `GuestPanel.tsx`, `GuestPanel.test.tsx`,
`QuickReplyPalette.tsx`. Five new tests (four for the four findings, one for the Ctrl+Enter half of
F1). Before fixing, each new test was run against the pre-fix code and failed — regression tests,
not descriptions:

```
$ npx vitest run src/features/inbox/Composer.test.tsx src/features/inbox/GuestPanel.test.tsx
×  GuestPanel > says so when the stay history cannot be loaded, rather than None
×  Composer > releases the forced palette as soon as you type, so Enter still makes a newline
×  Composer > disarms a picked asset when the draft is posted as a note instead
×  Composer > keeps a focus indicator in Note mode
Tests  4 failed | 42 passed (46)
```

After the fixes, the four suites covering the amended code — `QuickReplyPalette.test.tsx` included,
since that file changed:

```
$ npx vitest run src/features/inbox/Composer.test.tsx src/features/inbox/GuestPanel.test.tsx \
    src/features/inbox/QuickReplyPalette.test.tsx src/features/inbox/ConversationView.test.tsx

 ✓ src/features/inbox/GuestPanel.test.tsx (13 tests) 438ms
 ✓ src/features/inbox/QuickReplyPalette.test.tsx (16 tests) 565ms
 ✓ src/features/inbox/ConversationView.test.tsx (6 tests) 1084ms
 ✓ src/features/inbox/Composer.test.tsx (33 tests) 7828ms

 Test Files  4 passed (4)
      Tests  68 passed (68)
```

```
$ npx tsc -b
TSC_CLEAN exit=0

$ npm run lint
> eslint src --ext .ts,.tsx
LINT exit=0
```

## One new concern, not mine to fix

**`main` is currently red, from the other wave.** The full suite now reports
`386 tests, 1 failed`. The failure is `src/api/types.generated.test.ts` —
"`web/src/api/types.generated.ts` is stale relative to `web/src/api/schema.json` — run
`npm run gen:types` and commit the result". All three of the server commits that landed after my
wave (`2ba6cb8`, `182c459`, `554a950`) modified `web/src/api/schema.json` and none of them
regenerated the types.

This is not mine and it is not caused by this fix round. I confirmed that by stashing my changes and
running that one test against a clean `554a950`:

```
$ git stash && npx vitest run src/api/types.generated.test.ts
×  generated API types > are exactly what the generator produces from the committed schema
Tests  1 failed | 1 passed (2)
```

I did not run `npm run gen:types`. Regenerating would pull the new property-settings, departments-
CRUD and quick-reply-locale surface into the client's type file, which is R2/R3 territory, and the
commit belongs with whoever owns those endpoints. Excluding that one pre-existing failure, the suite
is **385 passing**.
