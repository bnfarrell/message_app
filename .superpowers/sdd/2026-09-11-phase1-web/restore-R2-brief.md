# Restoration R2 — Board & work orders: closed visibility, standalone create, standalone comment

> **Read `_CURRENT-CONTRACTS.md` in this directory first.** This brief predates waves
> R1, A1 and A2; that file carries the hazards, the error contract and the test-quality
> standard established since, and it wins wherever it disagrees with this brief.


Three affordances the approved mockups promise that the shipped board and work-order detail do
not have. All three are buildable today — the server supports every one. Line numbers below
were read from the current tree; a fix wave landed just before you, so **verify each anchor
before editing** and report any that moved.

Mockup authority: `docs/mockups/Board.dc.html` and `docs/mockups/WorkOrder.dc.html`.

---

## R2.1 — Verified and cancelled work orders are permanently invisible

**The gap.** `Board.dc.html:174` renders a control:

```
Verified and cancelled hidden · show 46 closed this week
```

`BoardPage.tsx` calls `useWorkOrders({ mine, dept })` and **never passes `includeClosed`** —
though the hook supports it (`web/src/api/hooks/workOrders.ts`) and so does the server
(`WorkOrderListQuery.include_closed`, `server/app/api/work_orders.py:98`). The board also only
iterates the five open `BOARD_COLUMNS`, so even fetched closed rows would not render.

Consequence: **a supervisor cannot review what was verified this week from anywhere in the
product.** There is no other screen that shows closed work orders.

Requirements:
- Add a toggle in the board's footer area matching the mockup's wording and placement: the
  muted "Verified and cancelled hidden" text with an accent-coloured action to reveal them.
- Drive it from a URL param (e.g. `?closed=1`) so the state survives a reload and is linkable,
  consistent with how the board's existing filters work. **Read how `BoardPage` handles its
  current query params and follow that pattern exactly** — note a fix wave just corrected the
  "All" tab's param handling, so read the current code, not your assumptions.
- When enabled, pass `includeClosed` to `useWorkOrders`.
- Render the revealed rows. The five open columns must not silently absorb them — `verified`
  and `cancelled` are terminal states and need their own home. **Pick one and justify it in
  your report:** a sixth column, or a distinct section below the board. Consider that the list
  view may be the more natural surface for closed history than the kanban columns.
- The mockup's count ("46 closed this week") is illustrative. Render a real count from real
  data, or omit the count — **do not fabricate a number or a "this week" window that the query
  does not actually apply.**

## R2.2 — You cannot raise a work order that is not attached to a conversation

**The gap.** `Board.dc.html:69` has a primary **New** button in the board header.
`BoardPage.tsx` ships only a Board/List view toggle. `CreateWorkOrderModal` requires a
`conversationId: string` prop and seeds itself from `useWorkOrderPrefill`.

But `CreateWorkOrder.source_conversation_id` is **optional** server-side
(`server/app/schemas/work_orders.py:25`) — and the mockups are full of work orders that have no
guest conversation behind them: `Board.dc.html` shows "POOL PUMP", "3F ICE", "ELEV B". **None
of those can be created in the shipped product.**

Requirements:
- Make `conversationId` optional on `CreateWorkOrderModal`. When absent: skip the
  `useWorkOrderPrefill` query entirely (do not call it with a placeholder id) and open an empty
  form.
- Add the **New** button to the board header, styled as the mockup's primary button, gated on
  `can('create_work_order')`.
- Every field the prefill would have filled must be editable and must validate when empty —
  work through what the form requires without a conversation behind it (title, department,
  priority, location) and make sure the POST body omits `sourceConversationId` rather than
  sending null/empty string, unless the schema accepts null.
- The conversation-attached path must keep working exactly as it does today. **This is a
  refactor of a working component — do not regress it.** Its existing tests must still pass
  unmodified; if you believe one must change, say why in your report rather than editing it
  quietly.

## R2.3 — A work-order comment can only be left as part of a status transition

**The gap.** `WorkOrder.dc.html:130-131` shows a standalone comment box:

```
Comment
[ Add a note for the team… ]
```

`WorkOrderDetailPage.tsx` has none. The only path to `WorkOrderPatch.comment` is
`TransitionButtons.tsx`, and only for the two statuses that require a reason. The server's
standalone branch (`server/app/api/work_orders.py:87` — `elif p.comment: work_orders.comment(...)`)
is **unreachable from the client.**

Requirements:
- Add a textarea plus a Comment button in the work-order detail, placed as the mockup places it
  (its own `Comment` section, under the Timeline).
- Submit via `usePatchWorkOrder(id).mutate({ comment })` — comment only, no status change.
- Gate it on the capability the server actually enforces for this route. **Read
  `server/app/api/work_orders.py` and match it**; do not guess, and do not invent a new
  capability.
- Clear the textarea on success and invalidate the work-order detail query so the comment
  appears in the Timeline immediately.
- Disable the button for an empty or whitespace-only comment.
- The existing transition-with-reason flow must keep working unchanged.

---

## Constraints

- TypeScript `strict`. No `any`; no `@ts-ignore` without a comment naming the reason.
- **No hardcoded hex anywhere.** All colour comes from the tokens in `web/src/index.css`,
  mapped into Tailwind by name.
- **Status colours are reserved and never decorative:** green = ok, amber = warn, blue =
  accent/primary action, red = danger.
- Radii are three values: **6 px** `rounded-md` (tags, badges, avatars, SLA chip), **8 px**
  `rounded` (buttons, inputs, nav rows), **10 px** `rounded-card` (cards, message bubbles).
- Server state lives **only** in TanStack Query. No server data in React state or context.
- Fonts: **do not assume Space Grotesk.** The shell/reskin wave (S1) runs BEFORE this one and
  changes the UI face. Read `web/src/index.css` for the current stack rather than hardcoding a
  family; mono is still used for room numbers, timers, ids and counts.
- Follow the existing component and test patterns in `web/src/features/board/`.
- Verify both themes — light is a real, supported mode.

## Tests (required)

- The closed toggle actually changes what is fetched and what renders, and its URL param
  round-trips.
- `CreateWorkOrderModal` opens and submits with no conversation, and the conversation-attached
  path still prefills.
- A standalone comment posts and appears, and the button is disabled when empty.

Each test must fail if the behavior it names breaks. An assertion that passes for an incidental
reason is a defect even when green — one such test was already caught on this branch.

## Verification before you commit

```
cd web && npm test && npx tsc -b && npm run build
```

All existing tests must still pass, plus yours. Output must be pristine — stray warnings are
findings against you. Do not run the Playwright E2E suite; it boots two servers and is slow.

Commit in three logical commits, one per item.
