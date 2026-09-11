# T1 — the Triage screen

Web only. One new screen, built from a Claude Design prototype, in **Relay's existing visual
language**.

**Read `_CURRENT-CONTRACTS.md` in this directory first.** It carries the hazards and the error
contract in force and wins wherever it disagrees with this brief.

## Where this came from, and the one thing not to get wrong

The user has a Claude Design project, "Relay hotel management software", containing two files:

- **`Relay Triage.dc.html`** — a working interactive prototype of a new supervisor screen.
- **`Relay Directions.dc.html`** — three *alternatives* to it (1b act-in-place, 1c dense console,
  1d time-to-breach), each with a trade-off note. It says outright: "The built prototype is the
  fourth option."

The user asked for the **prototype** (queue plus detail pane), and chose to have it built in
**Relay's current design** — the navy rail, Inter, the existing palette tokens.

**So do NOT copy the prototype's styling.** It uses its own "Broadsheet" system: Source Serif 4,
warm paper `#f3f2f2`, magenta `#d6006c`, teal `#006786`, 2px radii, hairline rules and no cards.
That is a different product's look, and adopting it here was explicitly declined. **Take the
information architecture and the behaviour; render it in our tokens.** If you find yourself
typing a hex, you have gone wrong.

## What the prototype actually is

A supervisor's cross-department escalation view. Left: a queue of everything open, ordered by how
far past its SLA it is. Right: a detail pane for the selected item, with route/priority/status
controls, the guest's SMS thread, an activity timeline, a note box, and a "tell the guest it is
fixed" action.

**Build only the Triage part.** The prototype also has Board and Shift tabs; we already have a
Board screen and an Analytics screen that cover them, and rebuilding either would be duplicate
product surface. If you think some detail of those tabs is genuinely missing from what we have,
say so in your report rather than building it.

## It maps onto endpoints that already exist — check each rather than trusting me

The design was generated from this repo's own schemas, which is why it lines up. Verify each of
these against the source before relying on it:

- `WorkOrderOut` carries `priority`, `status`, `departmentId`, `assignedUserId`,
  `sourceConversationId`, and crucially **`dueAt`** — the SLA deadline. "18m past SLA" is
  `now - dueAt`. Sort the queue by `dueAt` ascending so the most overdue is first.
- **`guestNotifiedAt`** is the prototype's `notified` flag. A work order that is `complete` or
  `verified` with a null `guestNotifiedAt` is the design's "guest not told" state, and it is one
  of the more valuable things on the screen — a resolved problem the guest still thinks is open.
- `GET work-orders` already filters by `status`, `type`, `dept`, `assignee`, `mine` and
  `includeClosed`. There is no server-side sort; sort client-side.
- `WorkOrderDetail` returns `events` (the activity timeline), `photos`, `guestName` and
  `roomNumber` — everything the detail pane shows.
- The guest thread comes from `sourceConversationId`. A work order raised from the floor has
  none, and the prototype handles that (its Lobby spill has an empty thread). Handle it too.

## Reuse rather than rebuild

`web/src/features/board/` already has `TransitionButtons`, `CommentBox`, `WorkOrderCard` and
`WorkOrderDetailPage`. The detail pane is largely those pieces in a narrower column. **Do not
write a second status-transition control** — `transitions.ts` encodes the legal state machine and
a parallel copy would drift from it.

## The mutation gate — read this before wiring Route to / Priority

The prototype's detail pane changes department, priority and status. On this server,
`PATCH /work-orders/<id>` currently enforces only auth plus property membership, with a
`close_work_order` check on closing statuses only — so it is **under-gated**, and a fix is queued
(ruling D110) mapping assign/department to `assign`, priority and non-closing status to
`create_work_order`, and closing statuses to `close_work_order`.

**Gate the client controls on those capabilities now**, so the screen is correct once the server
catches up and never offers an action that will 403. Check `web/src/auth/capabilities.ts` for the
real names. Corporate in particular must not be offered routing or priority.

## Who sees Triage

It needs a rail entry in `web/src/components/navModel.ts`, which also feeds the Ctrl+K palette —
they share `visibleNavGroups`, so adding it in one place covers both. Choose its capability from
`permissions.py` and **justify the choice in your report**: it is a cross-department supervisor
view, so consider whether a `dept_staff` user — whose work-order list the server may already scope
to their own department — should see it at all. Do not invent a capability.

Note the rail's active-state matching uses a `match` list, because a sibling route (`work-orders/:id`)
must keep the Board pill lit. If Triage routes anywhere outside its own path, give it the same
treatment.

## Behaviour worth copying exactly

- The queue's ordering rule, including its tie-break: past-SLA first by how far past, and within
  that the prototype prefers `blocked`, then `in_progress`, `assigned`, `open`, then closed.
- Selecting a row keeps you on the screen. Nothing navigates away — that is the whole point of
  the direction the user chose over 1b.
- The header count: "N past SLA · M live".
- After a route or a status change, the activity timeline gains an entry. Ours come from the
  server's `events`, so refetch rather than fabricating one client-side.

## Constraints

- **No hardcoded hex.** Palette tokens mapped into Tailwind by name; the only sanctioned
  exception in the client is `PhoneFrame.tsx`.
- Server state lives only in TanStack Query. Invalidate the right keys after a mutation — the
  board reads the same list.
- Do not change the server.
- **Do not toggle the theme through the UI** — it persists to the server.
- **Check whether an API server is already listening on 127.0.0.1:5200 before starting one.**

## Verify before you commit

- The web suite — check `git log` for the current number and beat it. `npx tsc -b` clean with no
  `.d.ts` under `tests/`, `npm run lint` exit 0, `npm run build` clean. **Read stderr.**
- Cover the ordering rule, the "guest not told" state, the capability gating for a role that must
  not see the controls, and the no-guest-thread case. Mutation-test each.
- Exercise it in a browser, in both themes, as a role that can act and one that cannot.
  Screenshots into this workspace directory, never the repo root.

Commit in logical commits on `main`. End every commit message with:
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>

## Report

Full report to `triage-T1-report.md`: the capability you chose for the screen and why, what you
reused versus built, anything in the prototype you could not back with an existing endpoint, and
a "Found but not fixed" section.

Return in your final message ONLY: status, commit shas, a one-line test summary, and concerns.

If any instruction here is wrong — a field that does not exist, a component that is not reusable,
a test that cannot fail — **say so and do the correct thing instead.** Implementers here have
caught defects in brief text eleven times, several of them mine.
