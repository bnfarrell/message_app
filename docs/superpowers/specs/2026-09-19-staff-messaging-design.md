# Internal Staff Messaging — Design

**Date:** 2026-09-19
**Source:** feature request to match Kipsu Exceed FCX's "Messaging" screens (staff-to-staff chat, `images/image (6).png` and `images/image (7).png`), reviewed against `docs/design.md` and the current Phase 1 build (`docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md`).
**Status:** approved for planning.

---

## 0. What this is, and what it isn't

Relay's existing Inbox is **guest** messaging: one guest, one conversation, SMS/consent/TCPA rules, sentiment scoring. This spec adds a second, separate messaging surface: **staff talking to staff** — direct messages, ad-hoc named groups, and one auto-provisioned property-wide `#ALL` channel. There is no guest involvement anywhere in this feature.

`docs/design.md` does not mention staff-to-staff messaging at all — this is net-new scope, not a gap-fill against an existing section.

## 1. Why a new table family instead of extending `conversation`

`conversation`/`message` are guest-shaped: exactly one `guest_id`, SMS delivery status, consent checks at the send path, sentiment. `internal_note` is a deliberately separate table specifically so a bug in guest-message rendering cannot leak a note to a guest (design.md §5.3). Staff messaging has none of those concerns but does need something guest conversations don't: multi-participant membership (groups), per-user unread tracking, and editable rosters. Reusing `conversation` would mean nullable-guest creep on a table whose safety invariants are tested and load-bearing. A parallel, smaller table family keeps both units easy to reason about independently (per the "design for isolation" principle) and touches zero guest-messaging code.

## 2. Data model

Added to `app/models/` as a new module, `app/models/staff_messages.py`, and a new `StaffConversationKind` / `StaffConversationEventType`-style enum block in `app/schemas/enums.py`.

```
staff_conversation
  id, property_id → property,
  kind ENUM(dm, group, all),
  name (nullable — set for group/all, null for dm),
  avatar_url (nullable),
  created_by_user_id → user_account (nullable — null for the system-created `all` channel),
  last_message_at (nullable, indexed with property_id — drives conversation-list ordering)

staff_conversation_participant
  id, conversation_id → staff_conversation, user_id → user_account,
  joined_at, last_read_at (nullable)
  UNIQUE(conversation_id, user_id)

staff_message
  id, conversation_id → staff_conversation, property_id → property,
  author_user_id → user_account,
  body (nullable — a message may be image-only),
  photo_content_type (nullable), photo_byte_size (nullable),
  photo_data (LargeBinary, nullable, deferred — same pattern as `work_order_photo`:
    bytes live in the row because the deployment filesystem is ephemeral)
```

Notes:

- `kind=dm` conversations have exactly 2 participants and are looked up by participant pair on creation (starting a DM with someone you already have a thread with reopens it, matching the screenshots' "New Conversations" list only showing people with *no* existing thread).
- `kind=all` is a singleton per property: created in the same place a property is created (and in the seed script), with every active `property_membership` added as a participant. New memberships auto-join it (see §5).
- Unread state is derived, not stored redundantly: a conversation is unread for a user if `last_message_at > last_read_at` (or `last_read_at is null`). `last_read_at` is bumped when the user opens/views that conversation (mirrors how guest-conversation presence already works, minus the realtime presence broadcast — no "X is typing" for this feature, per scope).
- A message has either `body`, a photo, or both — not neither. Enforced in the domain layer, same style as other required-one-of checks in `app/domain/`.

## 3. API

New blueprint `app/api/staff_conversations.py`, `url_prefix="/api/p/<property_id>/staff-conversations"`, registered in `app/__init__.py` alongside the existing blueprints. All routes: `@require_auth`, `@require_property` — no new capability. Messaging between property staff is available to every role in `STAFF` (`app/auth/permissions.py`), matching the screenshots (front desk, housekeeping, F&B, managers all message freely) and the existing convention that any authenticated property member reaches this surface.

```
GET    /api/p/:pid/staff-conversations                 # list mine, ordered by last_message_at desc
POST   /api/p/:pid/staff-conversations                 # {kind: dm, userId} or {kind: group, name, userIds[]}
GET    /api/p/:pid/staff-conversations/:id
PATCH  /api/p/:pid/staff-conversations/:id              # rename / change avatar (group only)
POST   /api/p/:pid/staff-conversations/:id/participants # add member(s) (group only)
DELETE /api/p/:pid/staff-conversations/:id/participants/:userId  # remove member, or "leave" for self
GET    /api/p/:pid/staff-conversations/:id/messages?cursor=
POST   /api/p/:pid/staff-conversations/:id/messages     # multipart: body (text, optional) + photo (file, optional)
POST   /api/p/:pid/staff-conversations/:id/read         # bump last_read_at to now
GET    /api/p/:pid/staff-conversations/:id/messages/:messageId/photo   # serves bytes, like work-order photos

GET    /api/p/:pid/staff-directory                      # all property members with role/department,
                                                          # minus users already in a DM with me —
                                                          # backs the "New Conversations" list
```

All routes 404 (not 403) a conversation the caller isn't a participant of — same information-hiding stance already used for property isolation elsewhere in the API.

`kind=all` conversations reject `PATCH` (rename/avatar) and the participant-remove route (nobody can be kicked from `#ALL`); `POST /participants` is a no-op there since membership is automatic.

## 4. Realtime

No changes to `app/realtime/registry.py` or `broadcast.py`. Exactly the existing pattern:

```python
queue_event(db, property_id, "staff_message.created", {"conversationId": conversation.id})
```

broadcast property-wide (thin payload, no message content — consistent with how `message.created` already works for guest conversations). Any connected client refetches; the REST layer enforces participant membership, so a staff member who isn't in the conversation gets a socket ping they ignore (their fetch 404s) rather than any content ever reaching them. `staff_conversation.updated` fires the same way on rename/participant changes.

## 5. Notifications

A new message in a conversation where the recipient isn't actively viewing it creates a row in the existing `notification` table — `type="staff_message"`, `entity_type="staff_conversation"`, `entity_id=<conversation id>`, `title` = sender name, `body` = message preview (or "sent a photo"). This reuses the notification centre, its unread badge, and its realtime delivery exactly as-is; no new notification infrastructure.

`#ALL` auto-join: `app/domain/users.py`, where `property_membership` rows are created, also inserts a `staff_conversation_participant` row for that property's `all` channel. The property-creation path (and `seed/seed.py`) creates the `all` channel itself.

## 6. Frontend

New route `/app/messages` (and `/app/messages/:id`), new nav entry visible to every staff role (unlike Admin/Analytics, this isn't capability-gated). New feature folder `web/src/features/messages/`:

```
MessagesPage.tsx           # the whole three-part layout: conversation list, thread, directory
ConversationList.tsx       # "Active Conversations" — avatar, name/group name, last message
                            # preview, relative time, unread dot
NewConversationList.tsx    # "New Conversations" — staff directory grouped/labelled by role,
                            # filtered to exclude existing DMs; click starts a dm conversation
ThreadView.tsx             # message list + composer (text + image, reusing the existing
                            # photo-upload UI pattern from PhotoPanel.tsx)
GroupPanel.tsx             # create/edit group: avatar upload, name, member multi-select
                            # (the screenshots' "View Group" slide-over)
```

API hooks in `web/src/api/hooks/staffMessages.ts` following the existing `conversations.ts` hook shape (TanStack Query, invalidate-on-WS-event). Types generated the normal way via the Pydantic → JSON Schema → TS pipeline (`schemas/staff_messages.py` → `export_json_schema.py` → `types.generated.ts`).

Search bar in the screenshots ("Search posts for selected date range") is Kipsu's Hotel Log search control reused inconsistently across their app — it doesn't correspond to any real behavior on the messaging screen (no date range makes sense for a conversation list) and the messaging screen's search there just filters by name. This build implements a plain client-side name filter over the conversation list and directory, not a date-range control.

## 7. Non-goals for this pass

Typing indicators, per-message read receipts, full-text message search, conversation muting/pinning, and edit/delete of sent messages. None of these are blocked by the schema above (in particular, `last_read_at` could later become a per-message read cursor without a breaking change) — they're just not built now.

## 8. Testing

- Backend: pytest coverage for — DM creation dedupes to the existing thread; group create/rename/add/remove participant; `#ALL` cannot be renamed or have a participant removed; a non-participant gets 404 on every conversation-scoped route; a new `property_membership` is auto-joined to `#ALL`; unread derivation from `last_message_at`/`last_read_at`; photo upload size/type limits mirroring `work_orders.MAX_PHOTO_BYTES`.
- Frontend: component tests for `ConversationList` unread styling, `GroupPanel` member selection, `ThreadView` optimistic send, following the existing `*.test.tsx` colocated pattern.

## 9. Acceptance criteria

1. Staff member A can message staff member B who isn't in their department; the thread appears in both users' conversation lists within 2s of send (realtime, matching the existing `message.created` latency bar).
2. Starting a "new conversation" with someone you already have a DM with reopens the existing thread rather than creating a duplicate.
3. Creating a group with 3+ named members produces one conversation all of them see immediately; the creator can later add/remove members and the change is visible to all participants in realtime.
4. Every property member is a participant of `#ALL` on their first login; a message posted there reaches every staff member's conversation list.
5. A user with no unread messages in a conversation, who then receives one, sees an unread indicator that clears when they open the thread.
6. A staff member who is not a participant of a given conversation receives 404 from every route scoped to that conversation's id.
7. Sending a photo-only message (no text) works; the photo is retrievable only by conversation participants.
