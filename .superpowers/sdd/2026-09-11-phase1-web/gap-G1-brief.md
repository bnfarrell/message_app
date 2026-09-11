# G1 — the server half of the disclosed-gap fixes

Server only. A web wave (G2) consumes what you build, so the shapes you choose are the contract
it is briefed against.

**Read `_CURRENT-CONTRACTS.md` in this directory first.** It carries the hazards and the error
contract in force, and it wins wherever it disagrees with this brief.

These four gaps were disclosed to the user as deliberately unfixed. They chose to fix the ones
with an obviously-correct answer and to skip the ones that would need invented behaviour. Three
of the four are yours.

---

## 1. Analytics buckets hours in raw UTC, not the property's timezone

`server/app/domain/analytics.py` — `by_hour = Counter(m.sent_at.hour for m in inbound)`.

`sent_at` is UTC. The property's own zone is `Property.timezone`, an IANA name that is now
validated on write, and the seeded properties are `America/New_York` and `America/Chicago`. So a
duty manager reading "busiest hour" sees a chart shifted by four or five hours — 8am guest
traffic appears at noon. The by-day counter has the same fault, and worse consequences: a message
sent at 9pm New York time lands on the *following* date in UTC, so it is counted on the wrong day.

Fix both. Convert each timestamp into the property's zone before taking `.hour` or `.date()`.

Care needed:

- `sent_at` may be naive in the database even though it is conceptually UTC — check how
  `UTCDateTime` hands it back, and attach UTC explicitly before converting rather than letting
  `astimezone` assume the *server's* local zone. Getting this wrong on a machine that is not
  already UTC produces a subtly different bug rather than a visible one.
- `default_range` and the `since`/`until` filters are UTC instants. You are changing which
  *bucket* a message falls into, not which messages are in range. Do not shift the range
  boundaries as well, or you will double-apply the offset.
- `tzdata` is already a dependency, so `ZoneInfo` works on Windows and slim images.

Tests: a message at a UTC hour that falls in a different local hour must land in the local bucket
— pick a case that also crosses midnight, so the by-day fix is covered too. Assert against both
seeded zones, not just one, because a single-zone test passes for a hardcoded offset.

## 2. The seed contradicts itself and the spec

Three specific holes, all previously disclosed:

- **No guest has more than one stay.** 106 guests, 106 stays. So the guest panel's "Previous
  stays" section renders empty for everyone — including guests whose denormalised stay count says
  "4th stay", which is a visible self-contradiction on screen. Give at least two guests a
  genuine stay history, and make sure their `stayCount` and their actual rows agree.
- **Property B (Lakeside Inn) has zero conversations**, so switching property lands the user on
  an empty inbox and makes the switcher look broken. Give it a realistic handful.
- **There is no conversation without a stay**, which spec §8 calls for — a guest who texts without
  being in-house exercises a real branch (`room_number` is null, and quick-reply interpolation
  falls back).

Constraints:

- The seed is deterministic — `random.Random(42)`. Keep it that way; a seed that changes between
  runs breaks every test that counts anything.
- `run(reset=True)` is refused for non-SQLite URLs by design. Do not weaken that.
- **Expect to update tests that assert seed totals**, and update them to the new true numbers.
  **Never weaken an assertion to accommodate the change** — if a test asserted "106 guests" it
  should now assert the new count, not "more than 100".
- Check whether the analytics, board and inbox tests depend on the counts you are changing before
  you change them, so you know what you are about to break rather than discovering it.

## 3. Work-order photo upload — and you are choosing the storage

`docs/mockups/WorkOrder.dc.html:91-94` shows a **Photos** panel with an "+ Add photo" action and
photos captioned `Before · 18:47 · Eli` / `After · 18:56 · Eli`. Its timeline at line 111 records
`Eli · after photo attached · 18:56`. So a photo carries a **kind** (before/after), a **time**,
and an **author**, and attaching one is a timeline event.

**There is no upload infrastructure in this server at all** — no multipart handling, no binary
column, nothing. So you are adding the first, and the storage decision is the real work.

**Ruling: store the bytes in the database, not on disk.** The deployment target is Railway, whose
filesystem is ephemeral: a disk-backed photo would vanish on the next redeploy, silently, leaving
a work order referencing an image that no longer exists. There is no object storage in this
project and adding one is out of scope. Database bytes survive wherever `DATABASE_URL` points and
need no new infrastructure. If you believe this is wrong, say so with your reasoning rather than
doing it the other way.

What that implies, and what I want you to handle deliberately:

- A new model and migration. Columns at least: `property_id`, `work_order_id`, `kind`
  (before/after), `uploaded_by_user_id`, `content_type`, `byte_size`, the bytes, and the
  timestamp the mixin gives you.
- **Cap the size and validate the type on the server**, not just in the client. Accept a small
  set of image types and reject everything else with the project's 400 contract. Pick a cap you
  can defend and say why.
- Serve the bytes back from an endpoint with the correct `Content-Type`, gated exactly like every
  other property-scoped route so one property cannot read another's photos. This is the part
  most likely to leak — a photo id is a guessable handle if the route forgets `require_property`.
- Record a `WorkOrderEvent` when a photo is attached, as the mockup's timeline shows, and an
  `audit_log` row, as spec §6 requires of every mutation of this kind.
- Deleting a photo: decide whether it is allowed at all, and say which. The mockup does not show
  it. If you allow it, the same tenancy rule applies.

Tests: upload and read back; a type that must be rejected; a size over the cap; **a cross-property
read that must 403** (the acceptance-criterion-9 enumeration will cover the route automatically —
confirm it picked yours up); the timeline event exists; the audit row exists.

---

## Out of scope — do not build these

- Inbox / conversation search. The user was offered it and declined; Phase 1 has no search
  endpoint and adding one is a genuine new capability.
- Automations, blocked numbers, integrations. No models, no spec, and the mockup captions them
  Phase 2.
- The guest panel's "Work orders + New" — that is client work and belongs to G2.
- Any client change at all.

## Verify before you commit

- The full server suite. Check `git log` for the current count first and beat it; nothing may
  break except seed-count assertions you deliberately update.
- Whatever lint the server runs.
- **Check whether an API server is already listening on 127.0.0.1:5200 before starting one.** Two
  servers on that port silently break WebSocket delivery — you now have a guard that refuses the
  second, so do not defeat it.

Commit in logical commits on `main` — the three items are unrelated and should not share one. End
every commit message with:
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>

## Report

Full report to `gap-G1-report.md`: the timezone approach and why it cannot double-apply, exactly
what changed in the seed and which test numbers moved, the photo storage decision with the size
cap and the accepted types, and **the exact request/response shapes G2 must code against**. Plus
a "Found but not fixed" section.

Return in your final message ONLY: status, commit shas, a one-line test summary, and concerns.

If any instruction is wrong — an anchor that moved, a test that cannot fail, a claim about the
seed that turns out false — **say so and do the correct thing instead.** Implementers here have
caught defects in brief text nine times, several of them mine, and it has consistently been the
highest-value thing they did. Never state a seed fact without querying it first. Never make
production code less correct to make a test deterministic.
