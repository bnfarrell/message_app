# Hotel Log — Posts — Design

**Date:** 2026-09-19
**Status:** Approved for planning
**Authority:** This document is binding for the Hotel Log Posts build. Where it differs from
`docs/design.md` §5.4 or §6.8, this document wins, and the difference is called out in §11.

---

## 1. What this is and why

A chronological, property-wide feed that replaces the paper shift logbook. A member of staff posts
what the next shift needs to know, tags a department, @mentions the people it concerns, attaches a
photo, and — when the entry is critical — marks it as requiring acknowledgement from a named
audience. A supervisor can then see who has and has not acknowledged it.

The accountability claim is the point. A feed nobody is accountable for is a group chat, and Relay
already has one of those (`docs/superpowers/specs/2026-09-19-staff-messaging-design.md`).

### 1.1 Origin

The reference product (Kipsu exceed FCX, screenshots in `images/`) exposes a Hotel Log with five
tabs: Posts, Broadcasts, Followups, Wakeups, Lost & Found. **Only Posts is in scope here.** The
other four are separate features with a different shape — wakeups and followups are scheduled items
with a due time and a completion state, Broadcasts overlaps `docs/design.md` §6.3 Outreach, and Lost
& Found is a top-level nav item in its own right. Each gets its own spec.

### 1.2 Scope

In scope:

- Chronological feed, newest first, grouped by calendar day, with a pinned block above it.
- Post with body text, optional department tag, optional photo, @mentions of people and departments.
- Derived shift label (am / pm / overnight) on every entry.
- Pin and unpin, restricted by capability.
- Optional acknowledgement requirement with a named audience and a stable denominator.
- Link an entry to an existing work order or guest conversation.
- Realtime delivery of new entries and of pin/ack changes.

Out of scope, deliberately:

- Translation. `docs/design.md` §6.8 marks the provider `[CONFIRM]` and it is still unconfirmed.
- The Broadcasts, Followups, Wakeups and Lost & Found tabs.
- Editing or deleting an entry (see §4.4).
- Export.
- Creating a *new* work order from an entry. Linking an existing one is in scope; the create flow
  belongs with the Board work and would drag this spec into work-order UI.

---

## 2. Approach

A standalone vertical slice, laid out exactly like staff messaging: `app/models/log.py`,
`app/domain/log.py`, `app/api/log.py`, `app/schemas/log.py`, and `web/src/features/log/`.

Two alternatives were considered and rejected:

- **Model the log as a `StaffConversation` kind.** The feed, photos and realtime already work there.
  But a log entry needs a department tag, a pin flag, a shift label, an acknowledgement audience and
  two link columns — five columns that are meaningless on a DM — and it has no participant model at
  all. `StaffConversation`'s own docstring (`server/app/models/staff_messages.py:15`) records that it
  was deliberately kept separate from the guest conversation table for the same kind of reason.
- **Extract a shared "mentionable post" abstraction** across internal notes, staff messages and the
  log. Premature with three call sites that disagree about participants, audiences and lifetimes.

The slice reuses, without modification:

| Existing machinery | Where |
|---|---|
| Deferred-blob photo storage (ephemeral filesystem rationale) | `server/app/models/work_orders.py:67` |
| Multipart photo upload, size cap, type sniffing | `server/app/api/staff_messages.py:59`, `app/domain/work_orders.py` |
| Post-commit realtime event queue | `server/app/realtime/broadcast.py:44` |
| Notification creation | `server/app/domain/notifications.py` |
| Audit trail | `server/app/domain/audit.py` |
| Property isolation decorators and their test suite | `server/app/auth/decorators.py`, Task 5 suite |

---

## 3. Data model

Four new tables in `server/app/models/log.py`. Two new enums in `app/schemas/enums.py`: `Shift`
(`am | pm | overnight`) and `MentionTargetType` (`user | department`).

```
log_entry
  id                      str pk
  property_id             FK property.id            not null, indexed
  author_user_id          FK user_account.id        not null
  department_id           FK department.id          nullable      -- the department tag
  shift                   enum(am, pm, overnight)   not null      -- derived at write, then frozen
  body                    Text                      not null
  pinned                  bool                      not null, default false
  pinned_by_user_id       FK user_account.id        nullable
  pinned_at               UTCDateTime               nullable
  requires_ack            bool                      not null, default false
  ack_expected            JSON                      not null, default []
  linked_work_order_id    FK work_order.id          nullable
  linked_conversation_id  FK conversation.id        nullable
  created_at, updated_at                                          -- TimestampMixin

  Index on (property_id, created_at) for the feed query.
  Index on (property_id, pinned) for the pinned block.

log_entry_mention
  id                      str pk
  log_entry_id            FK log_entry.id           not null, indexed
  property_id             FK property.id            not null, indexed
  type                    enum(user, department)    not null
  target_id               str                       not null   -- user_account.id or department.id
  position                Integer                   not null   -- author's insertion order
  UniqueConstraint(log_entry_id, type, target_id)
  Index on (property_id, type, target_id) for the mentioning_me filter.

log_entry_photo
  id                      str pk
  log_entry_id            FK log_entry.id           not null, indexed
  property_id             FK property.id            not null, indexed
  uploaded_by_user_id     FK user_account.id        nullable
  content_type            String(40)                not null
  byte_size               Integer                   not null
  data                    LargeBinary               deferred

log_entry_ack
  id                      str pk
  log_entry_id            FK log_entry.id           not null, indexed
  property_id             FK property.id            not null, indexed
  user_id                 FK user_account.id        not null
  acknowledged_at         UTCDateTime               not null
  UniqueConstraint(log_entry_id, user_id)
```

At most one photo per entry, matching the staff-message precedent. `log_entry_photo` is a table
rather than columns on `log_entry` so that a second photo is a later migration rather than a
redesign, and so the blob is never in the feed query's row set.

### 3.1 Mentions depart from §5.4

`docs/design.md:313` specifies `mentions uuid[]` as a column on `log_entry`. This design uses the
`log_entry_mention` table above instead, for two reasons.

A flat uuid array cannot distinguish a person from a department, and the reference post in
`images/image (2).png` mentions both in one body (`@FRONT DESK @Jennifer Garcia @Shanie Carrillo
@Zuleika Ortiz`). So the type has to be stored alongside the id either way.

Given that, a table beats a JSON array of `{type, id}` objects because of the `mentioning_me` filter
in §4.2. Filtering inside a JSON array means `json_each` on SQLite and `jsonb_array_elements` on
PostgreSQL — SQLAlchemy does not paper over that difference, and `docs/design.md` §10.1 commits to
moving to PostgreSQL by changing `DATABASE_URL` alone. A join table makes that filter an ordinary
indexed join on both engines. `position` preserves the author's insertion order for rendering, which
is the only thing the array ordering was giving us.

The API still accepts and returns mentions as the array form in §4.3 — the table is a storage
decision, not a wire-format one.

### 3.2 `ack_expected` is a snapshot, not a live query

When an entry is posted with `requires_ack`, the author's chosen audience — any mix of people and
departments — is resolved immediately to a flat list of concrete user ids, the author removed, and
the result frozen in `ack_expected`. The acknowledgement denominator is `len(ack_expected)`.

The alternative, recomputing department membership on every read, was rejected: a handover note
written last night reading "7 of 9 acknowledged" would silently become "7 of 10" when somebody joins
housekeeping this morning, changing a historical record after the fact. The accepted cost is the
mirror case — a person who joins the department after the post is never asked to acknowledge it.
For a handover record, a stable denominator is worth more than catching the late joiner.

Only active members (`UserStatus.active`) are resolved into `ack_expected`. A disabled account
cannot acknowledge, so including it would make the denominator permanently unreachable.

If the resolved audience is empty — for example, a department whose only active member is the author
— the entry is created with `requires_ack = false` and `ack_expected = []`, so the UI never renders
"0 of 0 acknowledged".

### 3.3 Shift derivation

`Shift` is `am | pm | overnight`. It is computed once, at creation, from `created_at` converted to
the property's timezone (`property.timezone`, `server/app/models/core.py:37`) and compared against
boundaries read from `property.settings`:

```json
{"shift_boundaries": {"am": "07:00", "pm": "15:00", "overnight": "23:00"}}
```

Those three defaults apply when the key is absent. The boundaries partition the 24-hour clock: a
local time at or after `am` and before `pm` is `am`; at or after `pm` and before `overnight` is
`pm`; everything else — including times after midnight and before `am` — is `overnight`. The
overnight window is the one that wraps midnight, and it is the case the tests must cover.

The value is stored rather than derived on read so that editing the boundaries in settings does not
retroactively relabel history.

Pinning is not tied to the shift. `docs/design.md:518` says "pin important entries to the top of the
shift"; this design implements a pin that lasts until somebody unpins it, because expiring pins at a
shift boundary needs either a per-read boundary calculation or a scheduled job, and the overnight
wrap makes both subtle. The shift label remains on the entry, so a shift-scoped pin can be added
later without a data change.

---

## 4. API

`server/app/api/log.py`, blueprint prefix `/api/p/<property_id>/log-entries`, matching
`server/app/api/staff_messages.py:16`. Every route carries `@require_auth` and `@require_property`.

### 4.1 Routes

| Method | Path | Capability | Notes |
|---|---|---|---|
| GET | `""` | `view_log` | Feed. |
| POST | `""` | `post_log` | Create. `multipart/form-data` when a photo is attached, else JSON. |
| GET | `"/<id>"` | `view_log` | One entry, acks resolved to names. |
| POST | `"/<id>/ack"` | — | Acknowledge. Gated by membership of `ack_expected`. |
| POST | `"/<id>/pin"` | `pin_log_entry` | |
| DELETE | `"/<id>/pin"` | `pin_log_entry` | |
| GET | `"/<id>/photo"` | `view_log` | Blob, mirroring `staff_messages.py:86`. |
| GET | `"/mentionables"` | `view_log` | Active members and departments for the picker, one call. |

### 4.2 Feed query

`GET ""` returns two blocks:

```json
{"pinned": ["...entries..."], "entries": ["...entries..."], "next_cursor": "..."}
```

`pinned` holds every currently pinned entry for the property, newest first, unpaginated — pins are
few by construction. `entries` holds the chronological feed, newest first, cursor-paginated at 50
per page on `(created_at, id)`. A pinned entry also appears in `entries` at its chronological
position; the client renders the pinned block and does not remove it from the feed.

Filters, all optional and combinable, applied to `entries` only:

- `shift` — one of `am`, `pm`, `overnight`
- `department_id`
- `from`, `to` — ISO dates, inclusive, interpreted in the property timezone
- `mentioning_me` — boolean; true restricts to entries mentioning the caller, counting department
  mentions of a department the caller belongs to

`mentioning_me` is an `EXISTS` over `log_entry_mention` matching either
`type='user' AND target_id=<caller>` or `type='department' AND target_id IN (<caller's
departments>)`. It stays in the database rather than post-filtering a page in Python, which would
break the cursor.

### 4.3 Create

Body fields: `body` (required, non-empty after strip, max 4000 chars), `department_id` (optional),
`mentions` (optional, a `[{type, id}]` array, persisted as `log_entry_mention` rows in the order
given), `requires_ack` (optional bool), `ack_audience` (optional, same array shape; ignored unless
`requires_ack`), `linked_work_order_id`,
`linked_conversation_id` (optional). Optional `photo` file part, subject to the existing
`MAX_PHOTO_BYTES` cap and `sniff_image_type` check from `app/domain/work_orders.py`.

Every referenced id — department, mentioned user, mentioned department, work order, conversation —
is validated to belong to the calling property. A cross-property id is a validation failure, not a
silent drop.

### 4.4 Entries are immutable

There is no PATCH on `body`, and no delete. A logbook that can be quietly rewritten is not a
handover record, and the acknowledgement of an entry means nothing if the entry's text can change
after it is acknowledged. A correction is a new entry. `pinned` and the ack set are the only mutable
state, and both are audited.

---

## 5. Capabilities

Three additions to `CAPABILITIES` in `server/app/auth/permissions.py:6`:

```python
"view_log": STAFF,
"post_log": STAFF,
"pin_log_entry": {Role.supervisor, Role.manager, Role.admin},
```

Acknowledging requires no capability; it requires being in the entry's `ack_expected`. A user not in
that list who posts to `/ack` gets a 403. This keeps the acknowledgement record meaningful — an
acknowledgement from somebody who was never asked is noise in the audit trail.

---

## 6. Mentions and notifications

The composer's picker inserts a token into the body and records `{type, id}` in the request's
`mentions` array, one `log_entry_mention` row each. Nothing
parses the body text for `@`. `server/app/domain/notes.py:16`, the first-name regex resolver used by
internal notes, is left untouched — this design does not extend it, because first-name matching is
already ambiguous in the reference product's own user list (`images/image (7).png` shows Ana
Marquez, Ana Maria-Bonilla and Anabella Miles at one property).

On create, `domain/log.py`:

1. Expands each department mention to that department's active members.
2. Unions those with the directly-mentioned users.
3. Removes the author.
4. Calls `notifications.create` once per remaining user with type `log.mention`, title
   `"<Author first name> mentioned you in the hotel log"`, body the first 140 characters of the
   entry, `entity_type="log_entry"`, `entity_id=<entry id>`.

This is the call shape used at `server/app/domain/notes.py:40`. A department mention yields one
notification per member, not one per department. A user mentioned both directly and via a
department receives exactly one notification.

When `requires_ack` is set, members of `ack_expected` who were not otherwise mentioned additionally
receive a `log.ack_requested` notification. A user who is both mentioned and in `ack_expected`
receives only the `log.mention` one.

### 6.1 Rendering

The body is stored as the author typed it, tokens included, and rendered client-side by matching the
`mentions` array against the text. The token format is `@[<display name>](<type>:<id>)`. The
renderer escapes everything and never trusts the stored display name for lookup — the id is
authoritative, the display name is presentation only. A renamed user therefore shows their old name
on an old entry, which is correct for a historical record.

---

## 7. Frontend

`web/src/features/log/`:

| Component | Responsibility |
|---|---|
| `LogPage` | Route shell, tab strip, filters, feed query, pinned block |
| `LogComposer` | Body, department tag, mention picker, photo, ack toggle + audience picker |
| `MentionInput` | Textarea with `@`-triggered autocomplete over `/mentionables` |
| `LogEntryCard` | One entry: author, time, shift badge, department tag, body, photo, links |
| `AckBar` | Progress, outstanding names for supervisors, Acknowledge button |

Route `/app/log`, added to `web/src/routes.tsx` and to `web/src/components/navModel.ts`. Visible to
all staff roles; no `RequireCapability` wrapper, since `view_log` is `STAFF`.

The feed groups by calendar day in the property timezone with a `Today · 2 posts` heading, matching
the reference. The page is built with a tab strip whose only tab is Posts, so Wakeups and Followups
slot in later without restructuring the page.

`MentionInput` is the only genuinely new component; the others follow the existing card and list
idiom from `web/src/features/messages/`.

---

## 8. Realtime

Two events via `broadcast.queue_event`, property-wide (`user_id=None`):

- `log.entry.created` — payload `{"id": "..."}`
- `log.entry.updated` — payload `{"id": "..."}`, emitted on pin, unpin and ack

Two cases added to `invalidationsFor` in `web/src/api/ws.ts`, invalidating the feed query and, for
`log.entry.updated`, the entry detail query. This mirrors the whole realtime cost of staff
messaging.

---

## 9. Testing

Backend (pytest, `server/tests/`):

- Shift derivation at each boundary, with a non-UTC property timezone, and across midnight for the
  overnight window. Custom boundaries from `property.settings` and the default when absent.
- `ack_expected` snapshot: a user added to the audience department *after* the post is not expected
  and cannot acknowledge; a user removed from it is still expected.
- Disabled users are excluded from `ack_expected`.
- Empty resolved audience downgrades `requires_ack` to false.
- Ack idempotency: a second POST returns the existing ack, does not duplicate, does not re-audit.
- Ack by a user outside `ack_expected` is 403.
- Pin and unpin enforce `pin_log_entry`; an agent gets 403.
- Immutability: no route exists that changes `body`.
- Photo: oversize rejected, non-image rejected, round-trips through `GET /photo`.
- Mention fan-out: department mention notifies each active member once; author never notified; a
  user mentioned twice gets one notification.
- Mention rows round-trip in the author's insertion order via `position`.
- Cross-property ids in create are rejected.
- Feed: cursor pagination, each filter, `mentioning_me` including department membership, pinned
  block contents.
- All new routes added to the Task 5 property-isolation suite.

Frontend (vitest, `web/src/features/log/`):

- Composer validation and submit, including the combined photo + ack path.
- Mention picker inserts a token and records the id; selecting a department inserts a department
  token.
- Ack bar states: not required, required and outstanding, required and acknowledged by the viewer,
  supervisor view listing outstanding names.
- Day grouping and the pinned block.
- Realtime invalidation on each of the two events.

---

## 10. Acceptance criteria

1. A front desk agent posts a shift note tagging Housekeeping, mentioning two people and one
   department, with a photo. Both people and every active member of that department receive a
   notification; the author does not.
2. The entry appears in every connected staff client's feed without a refresh.
3. A supervisor marks an entry as requiring acknowledgement from Housekeeping. The entry shows
   "0 of N acknowledged" where N is the count of active Housekeeping members excluding the author.
   As members acknowledge, the count rises; the supervisor can see who is outstanding.
4. Somebody joining Housekeeping the next morning does not change that entry's denominator.
5. An agent cannot pin an entry; a supervisor can, and a pinned entry appears in the pinned block
   for all staff until unpinned.
6. An entry posted at 02:00 local time is labelled `overnight`; one at 08:00 is `am`.
7. No route exists that alters the body of a posted entry.
8. A user from another property cannot read, acknowledge or pin any entry, as verified by the
   property-isolation suite.

---

## 11. Deviations from `docs/design.md`

| §6.8 / §5.4 says | This design does | Why |
|---|---|---|
| `mentions uuid[]` on `log_entry` | A `log_entry_mention` table | Must distinguish person from department, and `mentioning_me` has to filter portably across SQLite and PostgreSQL (§3.1) |
| "Pin to the top of the shift" | Pin until unpinned | Shift-expiring pins need a boundary job; the overnight wrap makes it subtle (§3.3) |
| "Create a work order … from any entry" | Link an existing one | The create flow belongs with Board work (§1.2) |
| "Double-tap to translate" | Not built | Provider still `[CONFIRM]` (§1.2) |
| No acknowledgement audience named | Author names an audience; denominator is a snapshot | "Who has read this" needs a denominator to be an answer (§3.2) |
