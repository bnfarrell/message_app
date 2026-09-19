# Unified Hotel Guest Engagement & Operations Platform
## Design Document / Build Specification

**Version 1.0 — 10 September 2026**
**Name:** Relay

This document is written to be handed directly to Claude (or any competent engineer) as a build specification. It is deliberately prescriptive about data model, states, and acceptance criteria, because those are the things that go wrong when a spec is vague. Sections marked **[CONFIRM]** are assumptions you should validate before build starts.

---

## 1. Purpose and scope

### 1.1 What this is

A single web platform, one codebase and one database, that unifies:

- **Guest engagement** — two-way messaging between guests and hotel staff across SMS and a no-download web surface, plus proactive automated messaging across the stay lifecycle
- **Hotel operations** — work orders, housekeeping, preventative maintenance, shift checklists, internal logs, and the team communication that surrounds them

The commercial thesis is the same one Kipsu sells: a guest who will not phone the front desk *will* send a text, so problems surface while they can still be fixed, and a fixed problem does not become a one-star review. The operations half exists because a surfaced problem that nobody assigns to anybody is worthless.

### 1.2 Why one app instead of two

Kipsu's own weakness is that Engage and Exceed are separate systems with separate logins, acquired rather than built together. The whole advantage of building this yourself is closing that seam. The design principle throughout:

> **A guest message and the work order it generates are the same object graph. A staff member should never re-key anything, and should never have to ask "did anyone action that?"**

Concretely: a guest texts "the AC in 412 is broken" → an agent raises a work order from inside the conversation in one click → engineering gets it on their phone → when they close it, the agent is prompted to tell the guest → the guest is told. One thread, one audit trail.

### 1.3 The guest surface is not a downloaded app

This is the single most important design constraint and the easiest one to get wrong.

Guests will not download a hotel app for a two-night stay. Adoption dies instantly. So:

- **Primary guest channel is SMS.** Zero friction, universal, works on a dumbphone.
- **Secondary guest channel is a web surface** — a mobile-optimised page reached by a tokenised link sent over SMS, or a QR code in the room. No login, no install. It's a Progressive Web App the guest *may* add to their home screen, but never has to.
- Both channels write into the same conversation thread. A guest can start on SMS, tap the link for a richer view (menus, order status, checkout), and reply by SMS again. Staff see one continuous conversation.

The web surface earns its place by doing things SMS can't: browsable menus, structured request forms, visible request status, digital folio, and rich media.

### 1.4 Non-goals for v1

Explicitly out of scope, to keep the build tractable:

- Mobile keys / door lock integration
- Contactless check-in and ID verification
- Payments and folio settlement (display only, read from PMS)
- Revenue management, channel management, booking engine
- AI-generated guest replies **[CONFIRM — see §11.3, this is a live strategic question]**
- Multi-tenant SaaS (v1 is single-portfolio; see §12.4)

---

## 2. Assumptions to confirm

| # | Assumption | Impact if wrong |
|---|---|---|
| A1 | Single hotel group, 1–20 properties, not a product sold to others | Multi-tenancy has to be in the data model from day one — expensive to retrofit |
| A2 | Property is in the US, so TCPA governs outbound SMS | Consent flow and opt-out handling change materially |
| A3 | You have a PMS with an API or event feed (Opera Cloud, Mews, Cloudbeds, Apaleo, HotelKey) | Without it, guest data is manual entry and automated welcomes are impossible |
| A4 | Twilio (or similar) as SMS provider, with a provisioned local or toll-free number per property | Deliverability, cost, and 10DLC registration all flow from this |
| A5 | Staff have smartphones (personal or issued) with a browser | The staff mobile surface is a PWA, not a native app |
| A6 | English + Spanish at minimum for staff-facing UI | Back-of-house staffing reality in most US hotels |
| A7 | Peak concurrent guests messaging ≈ 5% of occupied rooms | Sizing for realtime infrastructure |

---

## 3. Users and roles

### 3.1 Personas

**Guest.** Unauthenticated or lightly authenticated. Wants: fast answers, to report a problem without a confrontation, to order things, to leave without queueing. Tolerance for friction: near zero.

**Front desk agent.** Lives in the shared inbox all shift. Handles many conversations at once between check-ins. Needs speed above all: quick replies, one-click routing, keyboard shortcuts.

**Department staff** (housekeeping, engineering, F&B, spa). Mostly on a phone, often mid-task, sometimes not a fluent English reader. Needs: a short list of what's assigned to them, big touch targets, one-tap status changes, translation.

**Supervisor** (housekeeping supervisor, chief engineer). Assigns work, inspects, unblocks. Needs a board view and real-time status.

**Duty manager / GM.** Wants to know what's on fire right now and what keeps recurring. Needs alerts on negative sentiment and an at-a-glance dashboard.

**Portfolio / corporate.** Cross-property comparison, quality assurance on how staff are talking to guests, standards compliance.

**Admin.** Configures automations, quick replies, digital assets, users, and templates. May be the GM wearing a second hat.

### 3.2 Permission matrix

| Capability | Guest | Agent | Dept staff | Supervisor | Manager | Admin | Corporate |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Send/receive own messages | ✓ | — | — | — | — | — | — |
| View all conversations (own property) | — | ✓ | own dept | ✓ | ✓ | ✓ | ✓ |
| Reply to guest | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Assign / transfer conversation | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Add internal note | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Archive conversation | — | ✓ | — | ✓ | ✓ | ✓ | — |
| Send Outreach broadcast | — | — | — | ✓ | ✓ | ✓ | — |
| Create work order | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Close work order | — | — | ✓ | ✓ | ✓ | ✓ | — |
| Approve purchase order | — | — | — | threshold | threshold | ✓ | ✓ |
| View property analytics | — | own stats | own stats | ✓ | ✓ | ✓ | ✓ |
| View cross-property analytics | — | — | — | — | — | — | ✓ |
| Manage users, automations, templates | — | — | — | — | — | ✓ | ✓ |
| Export conversation data | — | — | — | — | ✓ | ✓ | ✓ |

Roles are per-property. A regional manager holds a Manager role at several properties. Model this as a join table, not a single `role` column on the user.

---

## 4. Information architecture

```
GUEST SURFACE (no login, tokenised link)
├── Chat            ← the whole thing, really
├── Requests        ← structured forms: housekeeping, maintenance, amenities
├── Order           ← F&B menus → cart → order → live status
├── Explore         ← digital assets: maps, hours, local guide
└── My stay         ← room, dates, folio (read-only), express checkout

STAFF SURFACE (authenticated)
├── Inbox           ← the shared conversation queue          [default for agents]
│   ├── All / Mine / Unassigned / Overdue / Dept filters
│   └── Conversation view + guest context panel
├── Board           ← work orders + requests, kanban or list  [default for supervisors]
├── Housekeeping    ← room grid, assignments, inspection
├── Maintenance     ← work orders, PM schedule
├── Checklists      ← shift checklists + readings
├── Log             ← the hotel log / shift handover feed
├── Outreach        ← broadcast composer + history
├── Analytics       ← property and portfolio reporting        [default for managers]
└── Admin           ← users, automations, quick replies, assets, tags, settings
```

**Navigation defaults by role.** Do not show a housekeeper the Admin nav. The landing screen after login differs by role — agent lands in Inbox, housekeeper lands in their room list, GM lands in Analytics. This one decision does more for adoption than any amount of UI polish.

---

## 5. Data model

Written as PostgreSQL-flavoured schema. Every table has `id uuid pk`, `created_at`, `updated_at`. Soft-delete via `deleted_at` where noted.

### 5.1 Core

```
property
  id, name, code, timezone, address, phone,
  sms_number, whatsapp_number, brand, currency,
  logo_url, primary_color, settings jsonb

user_account
  id, email, phone, first_name, last_name,
  avatar_url, locale (default 'en'), status,
  password_hash | sso_subject, last_seen_at,
  notification_prefs jsonb

property_membership
  id, user_id → user_account, property_id → property,
  role enum(agent, dept_staff, supervisor, manager, admin, corporate),
  department_id → department (nullable),
  UNIQUE(user_id, property_id)

department
  id, property_id, name, type enum(front_desk, housekeeping,
    engineering, food_beverage, spa, security, valet, other),
  sms_subaddress (nullable — for dedicated F&B number),
  escalation_minutes int, active bool
```

### 5.2 Guests and stays

```
guest
  id, property_id, first_name, last_name,
  phone_e164 (indexed), email, locale,
  loyalty_program, loyalty_tier, loyalty_number,
  vip bool, pms_profile_id,
  sms_consent_status enum(unknown, opted_in, opted_out),
  sms_consent_at, sms_consent_source,
  notes_summary text          -- rolling staff-visible summary
  -- NOTE: guest is per-property so history follows the property,
  -- with optional guest_link table for portfolio-wide identity

stay
  id, guest_id, property_id, pms_reservation_id,
  room_number, room_type, rate_code,
  status enum(reserved, checked_in, checked_out, cancelled, no_show),
  arrival_date, departure_date,
  actual_checkin_at, actual_checkout_at,
  adults, children, group_code, market_segment,
  is_return_guest bool, stay_count int,
  raw_pms jsonb              -- keep the payload, you'll want it

guest_tag
  id, property_id, name, color, category enum(event, segment,
    preference, operational), auto_rule jsonb (nullable)

guest_tag_assignment
  guest_id, tag_id, stay_id (nullable), assigned_by, assigned_at
```

`guest_tag` with `stay_id` is what makes "message everyone in the Henderson wedding block" work. Tags applied at stay level expire with the stay; tags at guest level persist across visits (e.g. "allergic to feathers", "always requests high floor").

### 5.3 Conversations and messages

```
conversation
  id, property_id, guest_id, stay_id (nullable),
  status enum(open, snoozed, archived),
  assigned_user_id (nullable), assigned_department_id (nullable),
  channel_primary enum(sms, web, whatsapp, email),
  last_guest_message_at, last_staff_message_at,
  first_response_seconds int (nullable),
  sla_due_at (nullable),        -- drives the Overdue filter
  sentiment enum(positive, neutral, negative, unknown),
  sentiment_scored_at,
  resolution_category_id (nullable),
  snoozed_until (nullable),
  unread_by jsonb              -- {user_id: bool}

message
  id, conversation_id,
  direction enum(inbound, outbound),
  author_type enum(guest, staff, system, automation),
  author_user_id (nullable),
  channel enum(sms, web, whatsapp, email),
  body text,
  attachments jsonb,           -- [{url, mime, filename, size}]
  digital_asset_id (nullable),
  delivery_status enum(queued, sent, delivered, failed, undelivered),
  provider_message_id, provider_error_code,
  redacted bool default false,
  sent_at, delivered_at

internal_note
  id, conversation_id, author_user_id, body,
  mentions uuid[],             -- @user notifications
  created_at
  -- NEVER visible to guest. Separate table, not a message type.
  -- This separation is a safety property: a bug in message rendering
  -- cannot leak an internal note to a guest.

typing_indicator          -- ephemeral, Redis not Postgres
  conversation_id, user_id, expires_at

resolution_category
  id, property_id, name, parent_id (nullable), active bool
  -- e.g. Maintenance > HVAC, Service > Housekeeping delay,
  --      Billing > Disputed charge, Praise, Question > Amenity hours
```

**Design note on `internal_note`.** Kipsu users love the note feature. Making notes a separate table rather than a `message` with `visibility: internal` is a deliberate belt-and-braces choice — the query that builds the guest-facing thread physically cannot return a note.

### 5.4 Operations

```
work_order
  id, property_id, title, description,
  type enum(maintenance, housekeeping, guest_request, pm, other),
  priority enum(low, normal, high, urgent),
  status enum(open, assigned, in_progress, blocked, complete, verified, cancelled),
  location_type enum(room, public_area, equipment, other),
  location_ref,                -- room number / area name / asset id
  department_id, assigned_user_id (nullable),
  reported_by_user_id, source_conversation_id (nullable),
  source_message_id (nullable),
  attachments jsonb, due_at, started_at, completed_at, verified_at,
  guest_notified_at (nullable),
  recurrence_rule (nullable),  -- iCal RRULE for PM
  parent_pm_schedule_id (nullable)

  -- source_conversation_id is the seam-closer. It is what lets the
  -- system prompt the agent to tell the guest when the work is done.

work_order_event
  id, work_order_id, user_id, type, from_value, to_value,
  comment, created_at        -- full audit trail

asset
  id, property_id, name, category, location, model, serial,
  installed_at, warranty_expires_at, pm_schedule jsonb

room
  id, property_id, number, floor, type, beds,
  housekeeping_status enum(clean, dirty, in_progress, inspected,
    out_of_order, out_of_service),
  occupancy_status enum(vacant, occupied, arrival, departure, stayover),
  assigned_housekeeper_id (nullable),
  last_cleaned_at, last_inspected_at, notes

housekeeping_assignment
  id, property_id, room_id, housekeeper_id, shift_date,
  sequence int, credits decimal, type enum(departure, stayover,
    deep_clean, touch_up), checklist_id (nullable),
  status, started_at, completed_at, inspected_by, inspected_at,
  inspection_score int (nullable)

checklist_template
  id, property_id, name, department_id,
  schedule enum(daily, weekly, monthly, per_shift, adhoc),
  shift enum(am, pm, overnight, any),
  items jsonb   -- [{id, label, type: check|text|number|photo,
                --   required, min, max, unit}]
                -- number+unit covers pool chemistry, HVAC setpoints

checklist_instance
  id, template_id, property_id, assigned_user_id, due_date, shift,
  status enum(not_started, in_progress, complete, missed),
  responses jsonb, comments jsonb, completed_at

log_entry                     -- the hotel log / shift handover
  id, property_id, author_user_id, department_id (nullable),
  shift, body, attachments jsonb,
  mentions uuid[], pinned bool,
  linked_work_order_id (nullable), linked_conversation_id (nullable),
  acknowledged_by jsonb       -- {user_id: timestamp}

purchase_order
  id, property_id, requester_id, vendor, description,
  line_items jsonb, total_amount, currency, department_id,
  status enum(draft, submitted, approved, rejected, ordered, received),
  approval_chain jsonb, approved_by, approved_at, notes

key_log
  id, property_id, key_identifier, key_type,
  issued_to_user_id, issued_by_user_id, issued_at,
  returned_at, returned_to_user_id, qr_code, notes
```

### 5.5 Content and automation

```
quick_reply
  id, property_id, department_id (nullable),
  shortcut,                    -- "/wifi"
  title, body,                 -- supports {{guest_first_name}} etc
  category, locale, usage_count, active bool

digital_asset
  id, property_id, name, description, category,
  type enum(file, link, menu, map, form),
  file_url | external_url, short_url,
  thumbnail_url, department_id (nullable),
  active bool, valid_from, valid_until,
  send_count

automation
  id, property_id, name, active bool,
  trigger jsonb,   -- see §7
  conditions jsonb,
  action jsonb,
  quiet_hours jsonb,           -- {start: "21:00", end: "08:00", tz}
  last_run_at, run_count

outreach_campaign
  id, property_id, created_by, name,
  audience jsonb,  -- {type: all_inhouse | tags | rooms | floors |
                   --  arrivals_today | departures_today, values: [...]}
  body, digital_asset_id (nullable),
  scheduled_for, sent_at,
  status enum(draft, scheduled, sending, sent, cancelled),
  recipient_count, delivered_count, replied_count,
  is_emergency bool            -- bypasses quiet hours & opt-out for
                               -- genuine life-safety only; audited
```

**On `is_emergency`.** Overriding opt-out is legally defensible for evacuation instructions and legally indefensible for a happy hour promotion. Gate it behind a Manager+ role, force a written justification, log it immutably, and put a scary confirmation dialog in front of it.

### 5.6 Integration and audit

```
integration
  id, property_id, kind enum(pms, sms, whatsapp, ticketing, pos, review),
  provider, credentials jsonb (encrypted at rest),
  status, last_sync_at, last_error, config jsonb

sync_event
  id, integration_id, external_id, event_type,
  payload jsonb, processed_at, error, retry_count
  -- idempotency: UNIQUE(integration_id, external_id, event_type)

audit_log
  id, property_id, actor_user_id, action, entity_type, entity_id,
  before jsonb, after jsonb, ip, user_agent, created_at
  -- append-only; required for SOC 2 and for the "who told the guest
  -- we'd comp their room" conversation
```

---

## 6. Feature specifications

### 6.1 Shared inbox — the core screen

**Layout (desktop):** three columns.

```
┌──────────────┬─────────────────────────┬──────────────────┐
│ Queue        │ Conversation            │ Guest context    │
│              │                         │                  │
│ [All ▾]      │  ┌─────────────┐        │ Sarah Chen       │
│ Filters:     │  │ guest msg   │        │ Room 412 · 3 nts │
│  Unassigned  │  └─────────────┘        │ Gold · 4th stay  │
│  Mine        │        ┌─────────────┐  │ Dep. Fri 11am    │
│  Overdue     │        │ staff reply │  │                  │
│  Negative    │        └─────────────┘  │ Tags: [Wedding]  │
│  By dept     │                         │                  │
│              │  ⌁ internal note        │ Notes (3)        │
│ ▸ 412 Chen   │                         │ Open WOs (1)     │
│ ▸ 118 Ruiz   │  ┌───────────────────┐  │  #204 AC repair  │
│ ▸ 703 Okafor │  │ [/] type reply…   │  │  In progress     │
│              │  │ ⚡Quick 📎Asset 🔧WO│  │                  │
└──────────────┴─────────────────────────┴──────────────────┘
```

**Mobile:** single column, swipe between the three panes.

**Queue behaviour**

- Sorted by oldest-unanswered first, not newest-message-first. The point is that nobody waits.
- Visual state per row: unread dot, assignee avatar, SLA countdown chip that goes amber then red, sentiment indicator, channel icon.
- **Presence.** Show, in the row and in the conversation header, who else is currently viewing or typing. Kipsu's own users report double-replies because this fails. Implementation: Redis-backed presence with a 5s heartbeat and 10s expiry, pushed over WebSocket. Additionally show a soft warning banner — "Marcus is replying" — that appears the moment another user focuses the composer, not when they've typed a character.
- **Optimistic send with rollback.** Message appears immediately, greys out and shows a retry affordance if the provider rejects it.

**Composer**

- `/` opens quick-reply search. Typing filters by shortcut and body. Enter inserts with variables interpolated.
- Attach digital asset by picker; guest receives a short link plus a preview.
- **Create work order** button opens a modal pre-filled from conversation context (room, guest, last message as description, suggested department from keyword match). Saves with `source_conversation_id` set.
- Translation toggle: show inbound message in staff's locale, compose in staff's locale and send in guest's. **[CONFIRM — needs a translation provider; budget for it]**
- Character counter with SMS segment count. Staff should see "2 segments" before they send a 400-character essay.

**Archiving**

Kipsu users complain about mandatory archive-on-reply. Design around it:

- Replying does **not** archive. Conversations auto-move to a `Resolved` view when there's been no guest message for N hours (default 4) **and** no open linked work order.
- Explicit archive is one click and prompts optionally for a resolution category.
- Archived conversations reopen automatically on any new inbound message, retaining full history.

**Guest blocking.** Kipsu doesn't have it and reviewers want it. Include it: block by phone number at property or portfolio level, with a reason and an audit entry. Blocked inbound messages are stored but suppressed from the queue, visible in an Admin > Blocked view.

### 6.2 Guest web surface

Reached via tokenised URL: `https://stay.<hotel>.com/s/<opaque-token>`.

- Token is a 128-bit random value mapped to a `stay`, expiring 24h after checkout.
- **No PII in the URL.** No room number, no name, no reservation ID.
- Tapping the link does not authenticate the guest for anything sensitive — folio is display-only, no payment actions, no ability to change the reservation. **[CONFIRM — if you want folio settlement, that needs a real auth step, probably last-name + arrival-date challenge]**
- Rate-limit token access and log every access with IP.

**Screens**

1. **Chat** — the same thread as SMS, live. This is the default landing screen.
2. **Requests** — structured forms (extra towels, late checkout, wake-up call, report a problem). Each submission creates a message in the thread *and* a work order, so staff see it in both places. Structured beats freeform for routing accuracy.
3. **Order** — F&B menus from digital assets, cart, submit. Order becomes a work order routed to the F&B department with live status back to the guest.
4. **Explore** — the digital asset library, filtered to guest-visible items: property map, hours, local guide, spa menu.
5. **My stay** — room, dates, read-only folio if PMS supports it, and **express checkout** (one tap → notifies front desk and flips the room to departure/dirty for housekeeping).

**Design constraints for the guest surface:** loads in under 1.5s on 4G, works at 320px, no login wall, no cookie banner beyond what's legally required, respects `prefers-reduced-motion`, WCAG 2.1 AA.

### 6.3 Outreach (broadcast)

Composer with:

- **Audience builder**: all in-house / by tag / by floor / by room list / arrivals today / departures today / checked-out in last N days. Live recipient count updates as the audience narrows.
- **Preview as a specific guest** with variables interpolated, so nobody sends "Dear {{first_name}}" to 200 people.
- **Throttled send** through the SMS provider to avoid carrier filtering; show a progress bar.
- **Replies land in the normal inbox** as individual conversations, tagged with the campaign. This is essential — a broadcast that generates 40 replies into a black hole is worse than no broadcast.
- Quiet hours enforced by default; emergency override per §5.5.
- Post-send report: delivered, failed, replied, opt-outs generated.

### 6.4 Work orders and the closed loop

State machine:

```
open → assigned → in_progress → complete → verified
                       ↓
                    blocked → in_progress
   any → cancelled
```

- Creation sources: staff manual, from a conversation, from a guest structured request, from a PM schedule, from a failed checklist item, from a log entry.
- Assignment to a department (fans out to that department's staff) or a named individual.
- Photo attachment on create and on complete. Before/after photos are the single most useful thing engineering supervisors get out of a system like this.
- Escalation: if a work order at `urgent` is unacknowledged for N minutes, notify the department supervisor; then the duty manager.
- **On transition to `complete`, if `source_conversation_id` is set:** push a prompt into that conversation for the agent — *"Work order #204 (AC repair, 412) is complete. Let Sarah know?"* — with a one-click pre-drafted message they can edit. Do not auto-send; a human should confirm the room is actually habitable before telling the guest so.

That prompt is the highest-value twenty lines of code in this entire system. It is the thing Kipsu's split architecture cannot do cleanly.

### 6.5 Housekeeping

- **Room grid** — floor-by-floor colour-coded board: clean / dirty / in progress / inspected / OOO. Filter by status, floor, assignee.
- **Assignment** — supervisor drags rooms to housekeepers, or auto-assigns by credits/workload with a manual override. Assignments push to the housekeeper's phone.
- **Housekeeper view** — a plain ordered list of their rooms with a big status button each. Start → In progress → Ready for inspection. Attach photos. Nothing else on the screen.
- **Real-time supervisor notification** when a room is submitted for inspection, plus live visibility of which room each housekeeper is currently in.
- **Deep clean checklists and projects** pushed into a specific assignment (window tracks, mattress rotation) rather than living in a separate module.
- Room status syncs bidirectionally with the PMS where the API allows.

### 6.6 Preventative maintenance

- Templates with iCal RRULE recurrence attached to assets or locations.
- Generates work orders on schedule into the engineering queue.
- Compliance dashboard: percentage of PM completed on time, by asset category. This is what a brand inspector asks for.

### 6.7 Shift checklists

- Templates per department per shift, with typed items: checkbox, free text, **number with unit and min/max bounds**, and photo.
- Number-with-bounds is what makes pool chemistry and HVAC setpoints work. An out-of-range reading auto-creates a work order and alerts the supervisor.
- Instances generate on schedule, are assignable, save progress continuously, and support comments for handover.
- Missed checklists are visible on the manager dashboard, not silently forgotten.

### 6.8 Hotel log

A chronological property-wide feed replacing the paper logbook.

- Post with department tag, @mentions, attachments.
- Pin important entries to the top of the shift.
- Create a work order or link a conversation from any entry.
- **Acknowledge** button — supervisors can see who has read a critical entry. Handover accountability.
- Double-tap any post to translate. **[CONFIRM translation provider]**

### 6.9 Analytics

**Agent level:** conversations handled, average and median first-response time, messages sent, quick reply usage, work orders created.

**Property level:** conversation volume by hour/day/channel, first-response time distribution (p50/p90 — averages lie), SLA breach count, sentiment mix and trend, top resolution categories, work order volume by type and department, mean time to resolution, PM compliance, checklist completion, housekeeping rooms-per-hour and inspection pass rate, Outreach engagement.

**Portfolio level:** all of the above compared across properties, plus a QA sampling view that surfaces random conversations for review and a "response quality" flag workflow.

**The report that justifies the project:** conversations containing a complaint, split by whether a work order was raised and closed before departure, cross-referenced against subsequent survey score or public review. That is the ROI story, and you can only tell it because both halves live in one database.

### 6.10 Notifications

| Event | Recipient | Channels |
|---|---|---|
| New inbound guest message | Assigned user, else on-duty department | In-app, push, sound |
| Response overdue (SLA breach) | Assignee, then supervisor | In-app, push |
| Negative sentiment detected | Duty manager | In-app, push, optional SMS |
| Conversation assigned to you | Assignee | In-app, push |
| @mention in note or log | Mentioned user | In-app, push |
| Work order assigned | Assignee | In-app, push |
| Urgent WO unacknowledged | Supervisor → manager | Push, escalating |
| Room ready for inspection | HK supervisor | In-app, push |
| Checklist reading out of range | Supervisor | In-app, push |
| PO awaiting your approval | Approver | In-app, email |

**Reliability requirements**, because this is Kipsu's most-complained-about area:

- Delivery is queue-backed and retried, not fire-and-forget from the request thread.
- Every notification has a persisted record and an in-app notification centre, so a missed push is still recoverable.
- If a push fails and the message is still unread after 3 minutes, fall back to SMS for on-duty staff.
- Per-user quiet hours and per-category mute, with an override for urgent.
- Test-notification button in settings so staff can prove theirs works.

---

## 7. Automation engine

Rules are `trigger → conditions → action`, stored as JSON and edited through a form-based builder. Do not build a general-purpose scripting environment; a fixed vocabulary is safer and sufficient.

**Triggers**
`stay.checked_in`, `stay.checked_out`, `stay.reserved`, `stay.room_assigned`, `stay.arrival_delayed`, `stay.midpoint_reached`, `conversation.created`, `conversation.no_response_for(minutes)`, `conversation.sentiment_negative`, `message.received`, `message.keyword_match(list)`, `work_order.completed`, `work_order.overdue`, `schedule.cron(expr)`

**Conditions**
Room type, rate code, loyalty tier, VIP flag, tag present/absent, length of stay, market segment, arrival time window, channel, guest locale, first-time vs returning, time of day, day of week, property.

**Actions**
`send_message(template, delay)`, `send_asset(asset)`, `apply_tag(tag)`, `assign_to(user|department)`, `create_work_order(template)`, `notify(user|role, message)`, `set_sla(minutes)`, `escalate()`, `add_note(text)`

**Global guardrails, enforced by the engine, not by the rule author:**

1. Quiet hours suppress non-urgent outbound messages and queue them for the window opening.
2. Frequency cap — no more than N automated messages per stay (default 4). Guests hate being spammed by a hotel more than almost anything.
3. Never send an automated message into a conversation where a guest message is awaiting a human reply. Automation must not talk over a real complaint.
4. Opted-out guests receive nothing except emergency broadcasts.
5. Every automated message is visibly attributed in the staff view and logged with the rule that fired it.

**Ship with these rules preconfigured**, since they're the ones every property wants:

| Rule | Trigger | Action |
|---|---|---|
| Welcome | `stay.checked_in` + 10 min | Personalised welcome, attributed to checking-in agent, with WiFi asset |
| Loyalty greeting | `stay.checked_in` where tier ≥ Gold | Tier-appropriate acknowledgement |
| Pending room | `stay.arrival_delayed` | "Your room isn't quite ready — here's what's open meanwhile" + map asset |
| Mid-stay check | `stay.midpoint_reached` at 10:00 local | "How's everything so far?" |
| Departure eve | day before departure, 18:00 | Checkout info + express checkout link |
| Post-stay | `stay.checked_out` + 4 h | Thank you; review link only if sentiment was positive |
| Silent complaint catch | `conversation.sentiment_negative` | Notify duty manager, set SLA 5 min, tag `service_recovery` |
| Idle nudge | `conversation.no_response_for(15)` | Escalate to supervisor |

Note the conditional review solicitation. Asking an unhappy guest to review you publicly is an own goal, and enough platforms do it that not doing it is a differentiator.

---

## 8. Integrations

### 8.1 PMS

Prefer, in order: real-time event stream → webhooks → polling API → nightly file drop.

Required inbound events: reservation created/modified/cancelled, check-in, check-out, room assignment, room move, folio update (optional), guest profile update including loyalty tier.

Outbound where supported: room housekeeping status, guest message logging back to the reservation, express-checkout notification.

**Implementation guidance:** write a thin adapter interface with one concrete implementation per PMS. Normalise everything to the internal `stay` and `guest` shapes at the adapter boundary. Store the raw payload in `raw_pms`. Make every handler idempotent on `(integration_id, external_id, event_type)` — PMS vendors redeliver, sometimes enthusiastically.

```
interface PmsAdapter {
  subscribe(onEvent: (e: PmsEvent) => Promise<void>): void
  fetchReservation(id: string): Promise<NormalizedStay>
  fetchInHouse(propertyId: string): Promise<NormalizedStay[]>
  pushRoomStatus?(room: string, status: RoomStatus): Promise<void>
}
```

Build a **MockPmsAdapter** first, generating plausible arrivals, check-ins and departures on a timer. It lets you build and demo the entire product before a single vendor conversation, and it becomes your integration test fixture.

### 8.2 Messaging providers

- **SMS** — Twilio Programmable Messaging. One number per property; optionally a second for F&B. Webhook for inbound and for delivery status. **10DLC brand and campaign registration is required in the US and takes weeks — start it on day one of the project, not at launch.**
- **WhatsApp** — Twilio or Meta Cloud API. Template message approval required for business-initiated messages outside the 24-hour service window; the automated welcome will need an approved template.
- **Web chat** — your own WebSocket, no third party.
- **Apple Messages for Business / Google Business Messages / WeChat / LINE** — real but each is its own onboarding project. Defer past v1; design the `channel` enum and the adapter interface so adding one is a plugin, not a refactor.

```
interface ChannelAdapter {
  send(to: Recipient, msg: OutboundMessage): Promise<ProviderResult>
  parseInbound(payload: unknown): InboundMessage
  supportsRichMedia: boolean
  maxLength: number
}
```

### 8.3 Other

- **Translation** — DeepL or Google Cloud Translation, cached aggressively by content hash.
- **Sentiment** — start with a keyword/phrase list plus negation handling. It's unglamorous, it's transparent, it's debuggable, and for "broken", "dirty", "unacceptable", "refund", "manager" it works. Upgrade to a model later if the false-negative rate justifies it.
- **Review platforms** — v2. Push a review request link; ingest ratings for the ROI report.
- **POS** — v2, for F&B order fulfilment and posting to folio.

---

## 9. Non-functional requirements

### 9.1 Compliance — read this section twice

**TCPA (US SMS).** Getting this wrong is a statutory-damages-per-message problem, so it belongs in the data model rather than in a policy document.

- Capture explicit consent before the first outbound message. Acceptable sources: check-in form checkbox, PMS consent flag, guest texting the property first. Record source and timestamp in `guest.sms_consent_*`.
- Honour STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT automatically and immediately; confirm once; set `opted_out`. HELP returns contact info.
- The send path must check consent. Not the UI — the send path. A UI check is a suggestion; a send-path check is a control.
- Quiet hours default 21:00–08:00 local to the *guest's* number where determinable, else property local.
- Retain consent records for at least 4 years.

**GDPR / CCPA.** Lawful basis documented per processing purpose. Data subject access and erasure implemented as real endpoints, not a manual process — erasure must redact message bodies while preserving aggregate counts. Configurable retention, default 24 months for conversation content, with automatic purge.

**PCI.** Do not accept card numbers over messaging. Detect card-number patterns in inbound messages, auto-redact before storage, and warn staff. Guests will send card numbers by text; the system's job is to make that harmless.

**Accessibility.** WCAG 2.1 AA on both surfaces. The guest surface in particular is used by people with disabilities who may specifically prefer text over phone.

### 9.2 Security

- SSO for staff where available; TOTP MFA otherwise, mandatory for Manager and above.
- Session timeout 12 h for staff, configurable; shared front-desk terminals get a shorter idle lock.
- Encryption in transit (TLS 1.3) and at rest; integration credentials in a secrets manager, never in the database in plaintext.
- Row-level authorisation by property membership, enforced in a single middleware layer, tested with a property-isolation test suite.
- Append-only audit log on every mutation of guest data, message content, and permissions.
- Rate limiting on the guest surface and all webhooks; signature verification on every inbound webhook.
- Aim the architecture at SOC 2 Type II from the start — audit logging, access review, change management — even if you don't certify in year one.

### 9.3 Performance and reliability

| Metric | Target |
|---|---|
| Inbox load (100 conversations) | < 800 ms p95 |
| Message send → visible to other staff | < 500 ms p95 |
| Inbound SMS → visible in inbox | < 2 s p95 |
| Guest surface first contentful paint on 4G | < 1.5 s |
| Uptime | 99.9% (be honest; 99.99% is a big claim) |

- Realtime over WebSocket with automatic reconnect and gap-fill on reconnect. A front desk agent who reconnects must not miss a message that arrived while they were offline.
- Outbound sends go through a durable queue with retry and dead-letter. Never send from the HTTP request thread.
- The staff PWA must degrade gracefully offline: show cached data read-only, queue status changes, sync on reconnect. Housekeepers work in stairwells and basements.

---

## 10. Technical architecture

### 10.1 Recommended stack

```
Frontend    Next.js 15 (App Router) + TypeScript + Tailwind
            shadcn/ui components; TanStack Query for server state
            Both surfaces in one app, separate route groups:
              (guest)/s/[token]/...   and   (staff)/app/...

Realtime    WebSocket. Self-hosted (Socket.IO) or managed (Pusher,
            Ably). Redis for presence and typing indicators.

Backend     Next.js route handlers for CRUD;
            a separate Node worker service for queues and schedulers
            (do not run cron in a serverless function)

Database    PostgreSQL + Prisma. Row-level security optional but
            application-level property scoping is mandatory.

Queue       BullMQ on Redis, or SQS if you're on AWS.
            Jobs: outbound send, automation eval, PM generation,
            checklist generation, SLA sweeps, PMS sync, digests.

Storage     S3-compatible for attachments; signed URLs, short TTL.

Auth        Auth.js with SSO providers + credentials; TOTP MFA.

Hosting     Vercel + Neon/Supabase + Upstash for a fast start;
            AWS ECS + RDS + ElastiCache if compliance demands VPC
            isolation.

Observability  Sentry, structured logs, and a message-delivery
               dashboard you will look at every single day.
```

**Why this stack:** one language across both surfaces, one deploy, strong typing across the API boundary via shared types, and Claude generates high-quality code in it. If your team has existing expertise elsewhere, use that instead — none of the design above depends on the stack.

### 10.2 Service boundaries

```
┌─────────────────────────────────────────────────────┐
│  Web app (Next.js)                                  │
│  ├── (guest) routes    — token-authed, minimal      │
│  ├── (staff) routes    — session-authed, full       │
│  └── /api              — REST + webhook endpoints   │
└───────────────┬─────────────────────────────────────┘
                │
     ┌──────────┴──────────┬───────────────┐
     ▼                     ▼               ▼
┌─────────┐         ┌────────────┐   ┌──────────┐
│ Postgres│         │   Redis    │   │    S3    │
└─────────┘         │ queue+pres │   └──────────┘
     ▲              └─────┬──────┘
     │                    │
┌────┴────────────────────▼─────────────────────────┐
│  Worker service                                    │
│  ├── outbound message sender (rate-limited)        │
│  ├── automation evaluator                          │
│  ├── scheduler (PM, checklists, SLA sweep)         │
│  ├── PMS sync adapters                             │
│  └── sentiment + translation                       │
└────────────────────────────────────────────────────┘
     ▲                          ▲
     │                          │
  PMS API/stream          Twilio / Meta
```

### 10.3 API sketch

```
# Guest (token-authed)
GET    /api/g/:token/stay
GET    /api/g/:token/messages?cursor=
POST   /api/g/:token/messages
POST   /api/g/:token/requests
POST   /api/g/:token/orders
POST   /api/g/:token/checkout
GET    /api/g/:token/assets

# Staff (session-authed, property-scoped)
GET    /api/conversations?status=&assignee=&dept=&overdue=&cursor=
GET    /api/conversations/:id
POST   /api/conversations/:id/messages
POST   /api/conversations/:id/notes
PATCH  /api/conversations/:id            # assign, archive, snooze, categorise
POST   /api/work-orders
PATCH  /api/work-orders/:id
GET    /api/rooms
PATCH  /api/rooms/:id/status
POST   /api/housekeeping/assignments
GET    /api/checklists/instances
PATCH  /api/checklists/instances/:id
POST   /api/log-entries
POST   /api/outreach/campaigns
POST   /api/outreach/campaigns/:id/send
GET    /api/analytics/:report

# Webhooks (signature-verified)
POST   /api/hooks/twilio/inbound
POST   /api/hooks/twilio/status
POST   /api/hooks/pms/:integrationId

# WebSocket events
conversation.created | message.created | message.status_changed
conversation.assigned | typing.start | typing.stop | presence.update
work_order.created | work_order.updated | room.status_changed
notification.created
```

---

## 11. Build plan

### Phase 0 — Clickable prototype (days, not weeks)

Ask Claude for a single-file React artifact with in-memory state: inbox with three columns, a handful of seeded conversations, a guest chat view, and a work order modal. No backend, no persistence.

The point is to put something in front of your front desk manager and your chief engineer *this week* and find out what you got wrong before you've built anything expensive. Expect the room grid and the work order flow to change substantially after this.

### Phase 1 — MVP (target ~8 weeks)

The thinnest thing that is genuinely useful at one property.

- Auth, roles, single property
- Guest and stay records via **MockPmsAdapter**
- SMS inbound and outbound via Twilio, with consent and STOP handling
- Shared inbox: queue, conversation, assign, transfer, notes, archive, presence
- Quick replies and digital assets
- Work orders created from conversations, with the closed-loop completion prompt
- Staff PWA with push notifications
- Basic analytics: volume, first-response time, SLA breaches

**Ship criteria:** the front desk uses it for a full week instead of the old process and does not ask to go back.

### Phase 2 — Operations (~8 weeks)

- Housekeeping: room grid, assignments, housekeeper view, inspection
- Preventative maintenance with recurrence
- Shift checklists with typed readings and out-of-range work order creation
- Hotel log with mentions and acknowledgement
- Guest web surface: chat, requests, explore, express checkout
- Automation engine plus the eight default rules
- Outreach with tag-based audiences
- Real PMS integration replacing the mock

### Phase 3 — Depth (~8 weeks)

- Multi-property, portfolio analytics, cross-property QA review
- WhatsApp channel
- Translation across log, chat, and staff UI
- Purchase orders and key log
- F&B ordering with menus and status
- Sentiment detection and negative-feedback alerting
- Review request flow, conditional on sentiment

### Phase 4 — Differentiation

- Additional channels (Apple Messages for Business, Google Business Messages)
- The ROI report: complaints caught and resolved pre-departure, correlated to review and survey outcomes
- Predictive maintenance from work order history
- AI assistance **[CONFIRM — §11.3]**

### 11.1 Acceptance criteria for Phase 1

Written as testable statements, because "the inbox works" is not a specification.

1. An inbound SMS from an unknown number creates a conversation and appears in the inbox within 2 seconds.
2. An inbound SMS from a number matching an in-house guest attaches to that guest's existing conversation with stay context populated.
3. Two staff opening the same conversation both see a presence indicator within 2 seconds.
4. Sending a reply shows optimistically, and on provider failure shows a retry control with the error.
5. Texting STOP sets consent to `opted_out` within 5 seconds, sends one confirmation, and all subsequent non-emergency sends to that number are rejected at the send path with a logged reason.
6. Creating a work order from a conversation populates room, guest, and description without manual entry, and stores `source_conversation_id`.
7. Marking that work order complete surfaces a draft notification message in the originating conversation, unsent, editable.
8. A conversation with no staff reply for 15 minutes appears in the Overdue filter and notifies the assignee.
9. A staff member with `dept_staff` role at Property A receives 403 on every Property B resource. Verified by an automated isolation test suite.
10. An internal note never appears in any guest-facing payload. Verified by a test that asserts the guest message endpoint's response shape excludes the notes table entirely.

### 11.2 Seed data for development

Build a realistic seed script: 120 rooms across 6 floors, 85 in-house stays with varied loyalty tiers, 30 conversations at different ages and sentiments, 15 open work orders, a housekeeping board mid-shift, three departments, twelve staff across all roles. Development against an empty database produces UI that falls apart on contact with a real Tuesday.

### 11.3 The AI question — decide deliberately

Kipsu bet against chatbots and has publicly argued guests don't want them. Competitors are shipping AI-drafted replies and AI voice answering. You are building from scratch in 2026, so you get to choose rather than inherit.

The defensible middle position, and my recommendation:

- **Yes** to AI *assisting staff*: draft-a-reply the agent edits and sends, conversation summarisation on shift handover, auto-suggested resolution category, auto-suggested department routing, translation.
- **No** to AI *replacing staff* in the guest thread by default. No autonomous replies to guest complaints.
- **Maybe**, behind a property-level setting, to autonomous answers for a narrow, unambiguous FAQ set (WiFi password, pool hours, breakfast times) with instant human handoff on anything else and a visible "ask for a person" affordance.

The failure mode to avoid: a guest reports a genuine problem and gets a confident, wrong, automated reply. That's worse than no messaging at all, because it converts a fixable complaint into a story about how the hotel doesn't listen.

---

## 12. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| 10DLC/carrier registration delays launch | High | Start registration in week 1. It is bureaucratic and slow and nothing about it can be compressed later. |
| PMS integration is harder than the vendor claims | High | MockPmsAdapter from day one; treat real integration as a Phase 2 milestone with its own spike. |
| Staff don't adopt it and revert to radios and paper | High | Role-specific landing screens, ruthless simplicity in the department staff view, a named champion per department, and measure daily active use per role from week one. |
| Notification unreliability erodes trust | High | Queue-backed delivery, persisted notification centre, SMS fallback, per-user test button. This is the specific thing Kipsu users complain about. |
| TCPA violation | High | Consent enforced at the send path; legal review of the consent flow before first outbound message. |
| Guest surface adoption is low | Medium | It's a bonus layer, not the product. SMS carries the core experience regardless. Measure but don't panic. |
| Scope creep into a full PMS | Medium | The non-goals list in §1.4 is a contract. Revisit it quarterly, not weekly. |
| Building this costs more than licensing Kipsu | Medium | Run the numbers honestly at Phase 1 exit. Build is justified by the unified data model and portfolio-specific workflow, not by licence savings. |

---

## 13. How to work with Claude on this build

Practical notes, since that's the stated intent.

**Give it this document, then work module by module.** Don't ask for the whole system in one prompt. A good unit of work is "implement the shared inbox queue and conversation view per §6.1, against the schema in §5.3, with the acceptance criteria in §11.1 items 1–4."

**Start with the schema.** Get `schema.prisma` right and reviewed before any UI exists. Everything downstream is cheap to change; the data model is not.

**Ask for the tests alongside the code**, particularly for §11.1 items 5, 9 and 10 — consent enforcement, property isolation, and internal note leakage. Those three are the ones where a silent bug is a legal or reputational event rather than an inconvenience.

**Build the MockPmsAdapter early** and let Claude generate the fake event stream. It unblocks everything.

**Have Claude write the seed script before the UI.** Then every screen is developed against realistic density from the first render.

**Keep this document in the repo** as `docs/design.md` and update it when decisions change. It's the shared context that makes each new session productive rather than archaeological.

---

## Appendix A — Screen inventory

**Guest:** chat · requests · request confirmation · order menu · cart · order status · explore/assets · asset viewer · my stay · express checkout confirmation · opted-out notice

**Staff:** login · MFA · inbox (queue/conversation/context) · conversation search · guest profile · outreach composer · outreach history · work order board · work order detail · work order create modal · housekeeping room grid · housekeeper task list · inspection view · PM schedule · PM template editor · checklist instance · checklist template editor · hotel log feed · log composer · purchase order list/detail/approval · key log · analytics dashboards (agent/property/portfolio) · QA review queue · notification centre · admin: users · roles · departments · automations list · automation builder · quick replies · digital assets · tags · resolution categories · integrations · blocked numbers · audit log · property settings

## Appendix B — Glossary

**FCX** — frontline customer experience. **Closed loop** — a guest issue tracked from report through resolution back to guest notification. **Outreach** — one-to-many broadcast to a defined guest audience. **Digital asset** — a reusable file or link staff send into conversations. **Quick reply** — a saved response template. **Service recovery** — resolving a guest problem before departure to prevent a negative review. **SLA** — the target first-response time on a guest message. **PM** — preventative maintenance. **Stayover** — an occupied room whose guest is not departing today. **10DLC** — the US carrier registration regime for application-to-person SMS on standard long codes.
