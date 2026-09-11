# G2 — inbox and work-order gaps

Web only. Three items. G1 (server) lands first and item 3 consumes its endpoint.

**Read `_CURRENT-CONTRACTS.md` in this directory first** — the hazards and the error contract in
force. It wins wherever it disagrees with this brief. Read `gap-G1-report.md` for the exact photo
endpoint shapes; **it wins over this brief** on any disagreement about a shape.

---

## 1. The Reply / Note switch is confusing (USER-REPORTED)

**The user asked for this directly, looking at the running app: "can you make the note and reply
two buttons, it is a little confusing the way it is now."**

Today `Composer.tsx` renders two `ModeTab`s (defined at the foot of that file):
`rounded px-3 py-1 text-xs font-bold uppercase tracking-wide`, where the *inactive* one is bare
text (`text-text3`) and the active one gets `bg-surface` (reply) or `bg-noteBg` (note). Three
things make that hard to read:

- the inactive control has no button affordance at all — it looks like a label, so the pair does
  not read as a choice;
- the labels are 12px uppercase, the smallest type in the composer, for the most consequential
  decision in it;
- the active Reply state is `bg-surface` sitting on a `bg-surface2` track, which is a very small
  step — and a reviewer found that this relationship **inverts between themes** (raised in light,
  inset in dark), so the selected state does not even read the same way twice.

**Make them two real buttons of equal weight**, each unmistakably a button whether or not it is
selected, with a selected state that is obvious at a glance in both themes. Sentence-case labels
at normal control size; consider an icon on each. Name them for what they do — the reply one acts
on the guest, the note one does not, and the labels should make that impossible to misread.

**What NOT to do, and this is the important part: do not collapse this into two send buttons.**
Removing the mode and offering "Send reply" / "Add note" at submit time looks tidier and is more
dangerous. Right now the mode is visible the *entire time you are typing* — the textarea is
tinted with `noteBg`/`noteText`/`noteBorder` and the placeholder reads "Internal note — not sent
to the guest". That continuous signal is what stops an agent composing a staff-only note and
sending it to the guest. A deferred choice at submit time turns a mis-click into a message the
guest receives and cannot unsee. **Keep the mode, keep the tint, keep the placeholder.**

Belt and braces while you are here: the submit button currently reads `Send` or `Add note`. Make
the reply case name its destination — something that says the guest will receive it. A one-word
`Send` is the least informative label in the most consequential place.

Constraints that already bite in this exact file:

- `cn` resolves Tailwind conflicts via `tailwind-merge` now, but this file carries `!important`
  overrides (`!border-noteBorder`, `focus:!border-accent`) that exist because `Textarea`'s ONLY
  focus affordance is its border. **If you touch those classes, verify the focus ring in a real
  browser with `getComputedStyle`, in both themes** — the test that guards it asserts a className
  string and therefore cannot fail.
- Corporate reaches this composer and has `add_note` but NOT `reply`. It must see the note
  control and no reply affordance at all. `dept_staff` has `reply`. Verify both.

## 2. The guest panel has no work orders (M11)

`docs/mockups/Main.dc.html` shows a **Work orders** section in the guest panel with a **+ New**
action. The shipped panel has neither, so from a conversation you cannot see what is already
raised for that guest — which is exactly when an agent needs to know, and the reason they raise
duplicates.

Show the work orders associated with the conversation's guest, and offer creating one. Reuse what
already exists: the board's work-order hooks and `CreateWorkOrderModal` (which a restoration wave
made capable of standalone creation). Do not write a second creation path.

Gate **+ New** on `create_work_order`. Check what the guest-scoped work-order query actually
supports before assuming a filter exists — if there is no way to fetch work orders for a guest,
say so in your report rather than inventing a client-side filter over the whole board.

## 3. Work-order photos (consumes G1)

`docs/mockups/WorkOrder.dc.html:91-94` shows a **Photos** panel with **+ Add photo**, captions of
the form `Before · 18:47 · Eli`, and a timeline entry `Eli · after photo attached · 18:56`.

Build the panel against G1's endpoints. Per photo show its kind (before/after), its time and its
author, as the mockup captions them.

Care:

- **Validate type and size client-side too**, and say what is wrong in the UI rather than letting
  the user discover a 400 after a slow upload. G1's report names the accepted types and the cap.
- Show upload progress or at least a pending state — a photo is the slowest thing this product
  uploads, and a silent freeze reads as a broken screen.
- Handle the failure cases the server actually returns, using the shared `fieldErrors` normaliser
  rather than a second copy.
- Gate the add action on the capability G1 gates the endpoint on. Do not offer what will 403.

---

## Constraints

- **No hardcoded hex colours.** Palette tokens mapped into Tailwind by name; the only sanctioned
  exception in the client is `PhoneFrame.tsx`.
- Capabilities live in `web/src/auth/capabilities.ts` — the path is `auth/`, not `lib/`.
- Do not change the server. G1 owns it.
- **Do not toggle the theme through the UI** — it persists to the server, and agents have
  repeatedly mutated user records that way. Set it on the document element instead.
- **Check whether an API server is already listening on 127.0.0.1:5200 before starting one.**
  A guard now refuses the second; do not defeat it.

## Verify before you commit

- The web suite — check `git log` and G1's report for the current numbers and beat the web one.
  `npx tsc -b` clean with no `.d.ts` under `tests/`, `npm run lint` exit 0, `npm run build` clean.
  **Read stderr**: a green suite with React warnings in it is not a green suite.
- Exercise all three in a real browser. For item 1, do it as **both** an agent and a corporate
  user. Screenshots into this workspace directory, never the repo root.

Commit in logical commits on `main`, one per item. End every commit message with:
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>

## Report

Full report to `gap-G2-report.md`, including what you found about guest-scoped work-order
fetching, and a "Found but not fixed" section.

Return in your final message ONLY: status, commit shas, a one-line test summary, and concerns.

If any instruction is wrong — a hook that does not exist, a shape G1 built differently, a test
that cannot fail — **say so and do the correct thing instead.**
