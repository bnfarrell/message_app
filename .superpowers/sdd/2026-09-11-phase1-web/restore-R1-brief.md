# Restoration R1 — Inbox: internal notes, previous stays, composer buttons

Three affordances the approved mockups promise that the shipped inbox does not have. All three
are buildable today — the server and the API hooks already exist. Every line number below was
read from the current tree, but a fix wave landed just before you; **verify each anchor before
editing** and report any that moved.

Mockup authority: `docs/mockups/Main.dc.html` (dark) and `MainLight.dc.html` (light).

---

## R1.1 — Internal note composer (the most important item in this brief)

**The gap.** `web/src/api/hooks/conversations.ts` defines `useAddNote` and a repo-wide grep
finds **zero call sites**. `ConversationView.tsx` *renders* notes but nothing can create one.

Why it matters, concretely:
- The server has `POST /api/p/<pid>/conversations/<id>/notes` gated on the `add_note`
  capability (`server/app/api/conversations.py:78-88`).
- Spec line 28 lists "internal notes" as in-scope, and spec §6 requires an `audit_log` row for
  "note create" — a row nothing in the product can currently produce.
- **`add_note` is the ONLY conversation capability the `corporate` role holds**
  (`web/src/auth/capabilities.ts`). `Composer` returns `null` for corporate. So
  `casey@group.test` today has *zero* available actions anywhere in the inbox.

**Where it goes — this is a design call, because the mockup does not show the entry control.**
The mockup renders a finished note *in the thread* (`Main.dc.html:144-146`: an amber
`--noteBg`/`--noteBorder` block reading `INTERNAL · Ava — Raised WO #204 to Engineering…`),
and `MessageBubble` already renders exactly that. What is missing is the way to write one.

Build it as a **segmented Reply | Note toggle directly above the composer input.** Reasons:
the note appears in-thread, so the in-thread input is where it belongs; a toggle needs no new
screen real estate; and it keeps one text field rather than two competing ones.

Requirements:
- The toggle is visible when the user `can('add_note')`. **Gate it on `add_note`, NOT on
  `reply`** — that is the whole point, and getting this wrong re-breaks corporate.
- In **Note** mode: the send action calls `useAddNote`, the placeholder changes to something
  like "Internal note — not sent to the guest", and the input area is visually distinguished
  using the existing `--noteBg` / `--noteBorder` / `--noteText` tokens. **Do not hardcode a
  hex** — the palette lives in `web/src/index.css` and maps into Tailwind by name.
- In Note mode the outbound-SMS affordances that do not apply must not be shown: no segment
  counter, no quick replies, no asset picker. A note is not an SMS.
- **A note must be sendable for an opted-out guest.** Consent governs outbound SMS, not internal
  notes. Verify the opted-out path: today `Composer` disables outbound send for an opted-out
  guest — Note mode must remain usable. This is the single highest-risk interaction in this item.
- For a user who can `add_note` but not `reply` (corporate), the composer must render in Note
  mode and must not offer Reply.
- Invalidate the conversation detail query on success so the new note appears in the thread.

**Tests (required):** a note posts through `useAddNote` and appears in the thread; the toggle
is gated on `add_note` and not on `reply`; a corporate-shaped session gets a usable Note
composer; a note is sendable while the guest is opted out.

## R1.2 — Guest panel "Previous stays"

**The gap.** `Main.dc.html:218-221` shows a `Previous stays` panel section:

```
JUN 2026 · 2N · 1 conv · resolved
MAR 2026 · 4N · praise · 5★
```

`GuestPanel.tsx` ships Guest / Stay / Consent / Work orders / Prompts / Notes — no stay history.

**The data already exists and is already plumbed.** `useGuest` (`web/src/api/hooks/users.ts`)
has **zero call sites**, and `GuestDetail` is `{guest, stays: list[StayOut], conversationIds}`
(`server/app/schemas/users.py:52-55`) — precisely this section.

Requirements:
- Add a `Previous stays` section to `GuestPanel`, following the existing `panel-h` section
  pattern in that file. Match the mockup's mono, muted styling.
- Consume `useGuest`; do not write a new hook.
- Render each past stay as one line. Use whatever `StayOut` actually carries — **read the
  schema and render only real fields.** The mockup's line is illustrative; do not invent a
  rating or a conversation count if `StayOut` has no such field. If a field the mockup shows
  does not exist server-side, omit it and say so in your report.
- Exclude the *current* stay — it already has its own `Stay` section directly above.
- Handle the empty case (a first-time guest) the way the file's other sections handle empty.

## R1.3 — The composer's "Quick" and "Work order" buttons

**The gap.** `Main.dc.html:165-167` shows three ghost buttons under the composer: **Quick**,
**Asset**, **Work order**. Only Asset ships (`Composer.tsx`).

Consequence: the quick-reply palette is reachable only by typing a `/` prefix, which is
undiscoverable. That is the real loss of the three.

Requirements:
- Add **Quick**, which opens the same `QuickReplyPalette` the `/` prefix opens. Reuse the
  existing component and its existing open/close state — do not build a second palette.
- Add **Work order**, which opens the same `CreateWorkOrderModal` the conversation header
  already opens. Reuse it.
- Order them **Quick · Asset · Work order** as the mockup does.
- Gate each on its capability: Quick and Asset on `reply`, Work order on `create_work_order`.
- **Leave the header's existing "Create work order" action where it is.** Both entry points to
  the same modal is fine and is what the mockup implies (the header action is the one the
  draft-prompt flow uses). Do not remove or relocate it.
- These buttons do not appear in Note mode (see R1.1).

---

## Constraints

- TypeScript `strict`. No `any`; no `@ts-ignore` without a comment naming the reason.
- **No hardcoded hex anywhere.** All colour comes from the tokens in `web/src/index.css`,
  mapped into Tailwind by name.
- Radii are three values: **6 px** `rounded-md` (tags, badges, avatars, SLA chip), **8 px**
  `rounded` (buttons, inputs, nav rows), **10 px** `rounded-card` (cards, message bubbles).
- Server state lives **only** in TanStack Query. No server data in React state or context.
- Fonts: Space Grotesk for UI, JetBrains Mono for room numbers, timers, ids and counts.
- Follow the existing component and test patterns in `web/src/features/inbox/`.
- Verify both themes — light is a real, supported mode, not an afterthought.

## Verification before you commit

```
cd web && npm test && npx tsc -b && npm run build
```

All existing tests must still pass, plus yours. Output must be pristine — stray warnings are
findings against you. Do not run the Playwright E2E suite; it boots two servers and is slow.

Commit in three logical commits, one per item.

## Out of scope — do not build

The guest panel's "Work orders + New" affordance (`Main.dc.html:204`) and the inbox search box
(`Main.dc.html:38`, no server support in Phase 1). Both are being disclosed to the user instead.
Do not delete `useAddNote` or `useGuest` as dead code — you are their first consumer.
