# A2 — the quick-replies admin screen

Web only. One screen: `web/src/features/admin/QuickRepliesAdmin.tsx` (199 lines — read it all
before you start) and its test file.

## Read the A1 report first

Wave A1 added the server endpoints this wave consumes. **`admin-A1-report.md` in this directory
carries the exact request and response shapes — code against those, not against this brief's
description of them.** If A1's report and this brief disagree about a shape, A1's report wins
and you should say so in your report.

## What this screen is missing

`docs/mockups/Admin.dc.html` is the binding reference for this screen and it is the one screen
the mockups draw in full detail. Five things it promises that the shipped screen does not do.
Open the mockup and read lines 90–130 yourself.

### 1. The "Insert:" variable chips (mockup lines 111–115)

Under the Body field the mockup shows a row of clickable variable chips. Today there is a static
hint line instead:

```
{'{{guest_first_name}}'} and {'{{room_number}}'} are filled in when sent.
```

Replace it with real chips. Clicking a chip **inserts `{{variable_name}}` at the caret position
in the body textarea** — not appended at the end, and not replacing the selection silently
without the user seeing where it went. Keep focus in the textarea afterwards and put the caret
after the inserted token, so an admin can type straight on.

**Ruling D68 — render FIVE chips, not the mockup's four.**
`server/app/domain/quick_replies.py:15-16` defines `VARIABLES` as `guest_first_name`,
`room_number`, `property_name`, `agent_first_name`, `departure_date`. The mockup draws four and
omits `property_name`. The server is authoritative: a variable the renderer supports but the UI
never surfaces will never be used. Get the list from the server per A1's report rather than
hardcoding it in the client; if A1 decided the client should hold a shared constant instead, its
report will say so — follow that.

This is a deliberate, disclosed divergence from the mockup. Note it in your report.

### 2. The character and segment counter (mockup line 121)

The mockup shows `138 chars · 1 segment` under the preview.

**This is server-computed. Do not implement SMS segment counting in TypeScript.**
`server/app/domain/sms.py:22-29` implements GSM-7 vs UCS-2 with the 160/153 and 70/67
boundaries. That logic is subtle enough that an earlier task on this project shipped an
off-by-one in it, and a second copy in the client would be free to drift from the one that
actually bills the customer. A1 built a preview endpoint that returns `segments` and
`characters` precisely so this stays in one place.

Pluralise properly — `1 segment`, `2 segments`.

### 3. The live preview (mockup lines 118–120)

A preview pane showing the body with variables interpolated.

**Ruling: the preview uses A1's preview endpoint with NO conversation id**, so it renders
against the server's `FALLBACKS` map (`"there"`, `"your room"`, `"the front desk"`, `"soon"`).
Reasons, and they are not arbitrary:

- It must preview the **draft body as typed**, before Save. A stored-row render cannot do that.
- A property may have no conversations at all — Property B on this install has zero — so a
  preview that needs one is a preview that breaks on a real property.
- It stays deterministic. A preview that changes because someone answered a message is a
  confusing thing to put next to an edit form.

Label it honestly. The mockup says `Preview as Sarah Chen · 412`; with sample values that label
would be a lie. Use something like `Preview · sample values`. **Disclosed divergence — report it.**

Do NOT build a conversation picker. Do NOT fetch a conversation list on this screen.

**Debounce the preview request** (~300ms) so it does not fire per keystroke, and do not fire it
at all for an empty body. Handle its error and loading states — a preview pane that renders a
stale body while a request is in flight is worse than one that says it is updating.

### 4. The Category input (accepted gap 5, first half)

`category` is already in the `Draft` type, already sent on create, and already sent on patch.
**There is simply no input for it.** Add one. The mockup does not draw a category field, so this
is a disclosed addition rather than a fidelity fix — the server has supported it all along and
an admin currently cannot set it at all.

A free-text `Input` is right unless the existing rows suggest a fixed vocabulary — check what
values are actually in use before deciding, and say what you found.

### 5. The Locale input (accepted gap 5, second half) — and a comment that is now WRONG

`locale` is in the `Draft`, is sent on create, and is deliberately stripped from the patch
payload. The code says why:

```
// The server's QuickReplyPatch has no `locale` field (extra="forbid" rejects it), unlike
// QuickReplyIn on create — send only what patch actually accepts.
```

**A1 added `locale` to `QuickReplyPatch`, so that comment is now false.** Delete it, include
`locale` in the patch payload, and add an input for it. Confirm against `admin-A1-report.md`
that the field landed before you rely on it — if for any reason it did not, stop and report
rather than sending a field the server will reject.

## Also: match the mockup's panel layout

While you are in this panel, bring the field order to what the mockup draws (lines 104–122):
Shortcut and Department **side by side in a two-column grid**, then Title, then Body with the
chips beneath it, then the preview with its counter, then the Active toggle, then the
Save/Cancel/Delete row. The shipped order is Shortcut, Title, Body, Department, Active.

Keep using the existing `EditPanel`, `AdminTable`, `Input`, `Textarea`, `Button` and `Badge`
components. Do not introduce new UI primitives for this.

## The type pipeline — do not hand-write a type A1 already defined

Client types are **generated from the server's Pydantic models**, not written by hand:

```
server/app/schemas/export_json_schema.py  →  web/src/api/schema.json
npm run gen:types                          →  web/src/api/types.generated.ts
```

and `web/src/api/types.ts` then **re-exports the names by hand** — its own header says to import
from `types.ts`, never from `types.generated.ts`.

So for any new shape A1 added (the preview request and response, and anything else its report
names):

1. Check whether A1 already regenerated `schema.json`. If it did not, run the export and
   `npm run gen:types` yourself.
2. **Add the new type names to the re-export list in `web/src/api/types.ts`.** This is a manual
   step and it is the easy one to miss — without it the generated type exists but cannot be
   imported, and the temptation is to hand-write a duplicate interface in the component. Do not
   do that. A hand-written copy of a generated type is a copy free to drift from the server.
3. Keep the list's existing alphabetical grouping.

## Constraints

- **No hardcoded hex colours.** The palette is 45 CSS custom properties in `web/src/index.css`
  mapped into Tailwind by name. The only sanctioned exception in the client is `PhoneFrame.tsx`.
- **Capabilities live in `web/src/auth/capabilities.ts`** — note the path, it is `auth/`, not
  `lib/`. It mirrors `server/app/auth/permissions.py`.
- **`corporate` reaches this screen.** `manage_admin` is `{admin, corporate}`. A1's preview
  endpoint is gated on `manage_admin` specifically so corporate works — the older `/render`
  endpoint is gated on `reply`, which corporate does NOT have. If you find yourself calling
  `/render`, you have the wrong endpoint.
- **Beware `cn`.** It does not resolve Tailwind class conflicts and there is no `tailwind-merge`
  in this project: a `className` colour override can silently no-op, and tsc, lint and the test
  suite will all pass over it. If you override a colour class, verify in a browser with
  `getComputedStyle` that it actually applied.
- Do not touch any other admin screen. A3 owns Departments and Property settings.
- Do not change the server. A1 owns it.

## Verify before you commit

- The web suite. Check `git log` and the A1 report for the current count before you start, and
  beat it. Cover: chip insertion at the caret, the counter rendering from the server response,
  the preview debounce, `locale` surviving a patch round-trip, and category surviving one.
- `npx tsc -b` clean, no `.d.ts` under `tests/`. `npm run lint` exit 0. `npm run build` clean.
- **Exercise it against the real server.** `start.bat` cold-starts both halves; API on
  http://127.0.0.1:5200, web on http://127.0.0.1:5173, login `ava@hvh.test` / `Password123!`.
  Confirm with your own eyes that a chip inserts at the caret, the counter matches what the
  server returns, and the preview interpolates. **Then sign in as a `corporate` user and
  confirm the preview works for them too** — that role is the reason A1's endpoint exists.
  Put screenshots in this workspace directory, never in the repo root.

Commit in logical commits on `main`. End every commit message with:
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>

## Report

Full report to `admin-A2-report.md`: what you built, the chip list you got and from where, the
category vocabulary you found, the divergences from the mockup you are disclosing, and a
"Found but not fixed" section.

Return in your final message ONLY: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT /
BLOCKED), commit shas, a one-line test summary, and your concerns. Keep it short — that text
lands in the controller's context.

If any instruction above is wrong — a field that does not exist, a shape A1 built differently, a
test that cannot fail — **say so and do the correct thing instead.** Implementers on this
project have caught defects in brief text four times now and it has been the single
highest-value thing they did. Never make production code less correct to make a test
deterministic. Do not dispatch subagents.
