# Hotel Engagement Platform — Phase 1 MVP Design

**Date:** 2026-09-10
**Source spec:** `docs/design.md` (v1.0). This document narrows that spec to the Phase 1 MVP (§11 Phase 1, §11.1 acceptance criteria) and records the stack decisions that differ from it.
**Status:** approved for planning.

---

## 0. Decisions that differ from `docs/design.md`

| Area | Design doc says | This build does | Why |
|---|---|---|---|
| Backend | Next.js route handlers + Node worker, TypeScript | **Python 3.14 · Flask 3** app factory with blueprints; worker as a daemon thread in the same process | User preference for Python and Flask. |
| Database | PostgreSQL + Prisma | **SQLAlchemy 2.0 + Alembic on SQLite**; PostgreSQL later by changing `DATABASE_URL` (see §11) | User request: SQLite is easier to start. SQLAlchemy's `Enum`/`JSON` types and Alembic migrations work on both engines, so the move is configuration, not a rewrite. |
| API contracts | Shared TS types across one codebase | **Pydantic v2** request/response models on the server; JSON Schema exported and converted to TypeScript for the React client | Keeps typed contracts across a Python/TS boundary. Strict response models are also how criterion #10 is enforced. |
| Frontend | Next.js 15 App Router | **Vite + React 18 + TypeScript** SPA | User request. |
| Queue / presence | BullMQ + Redis | SQLite `job` table + in-memory presence dict, worker thread in-process | No Redis. Single process is correct for one property (§2 A7). Worker is a bounded module with `start()`/`stop()` so it can be split out later. |
| Realtime | WebSocket over Redis pub/sub | **flask-sock** plain WebSocket; direct in-process broadcast | Same reason. Frontend uses the browser's native `WebSocket`. |
| Auth | Auth.js + SSO + TOTP MFA | `bcrypt` + server-side session table + `HttpOnly` cookie. MFA/SSO deferred. | Single-property local MVP. Isolation and roles are fully built; MFA is a bolt-on. |
| SMS | Twilio | `MockSmsAdapter` behind the `ChannelAdapter` interface, plus a dev phone simulator | No credentials; 10DLC takes weeks. Consent, STOP, delivery status and failure handling are real; only the wire is fake. |
| PMS | Real vendor adapter | `MockPmsAdapter` | As the design doc itself recommends for Phase 1. |
| Push notifications | Staff PWA with browser push | Persisted in-app notification centre + realtime delivery; installable PWA manifest. Browser Web Push deferred. | The persisted `notification` table is the part §6.10 says matters; Web Push adds VAPID/service-worker plumbing without changing the model. |

Everything else follows `docs/design.md` for the Phase 1 feature set.

## 1. Scope

**In:** auth and per-property roles · guests and stays via `MockPmsAdapter` · mock SMS inbound/outbound with consent and STOP/HELP · shared inbox (queue, filters, conversation view, assign/transfer, internal notes, archive/reopen, snooze, presence, typing) · quick replies · digital assets · work orders with state machine, audit events, and the closed-loop completion prompt · notification centre · basic analytics · seed data · tests for §11.1.

**Out (deferred, data model does not block them):** housekeeping, preventative maintenance, checklists, hotel log, outreach, automation engine, guest tokenised web surface, guest tags, number blocking, sentiment, translation, WhatsApp, MFA/SSO, browser Web Push, real Twilio/PMS adapters, multi-property UI, offline PWA mode.

## 2. Repository layout

```
docs/design.md                    full v1.0 spec
docs/superpowers/specs/           this file
docs/superpowers/plans/           implementation plan
package.json                      root: `dev` (concurrently: server + web), `test`, `gen:types`
README.md

server/                           Python
  pyproject.toml                  deps, ruff, pytest config
  alembic.ini, alembic/           migrations (env.py reads DATABASE_URL)
  app/
    __init__.py                   create_app(config) — app factory
    config.py                     env-driven settings
    db.py                         engine, SessionLocal, Base, session_scope()
    models/                       SQLAlchemy models, one file per aggregate
    schemas/                      Pydantic models (requests, responses, enums), export_json_schema.py
    auth/                         passwords.py, sessions.py, decorators.py (require_auth, require_property, require_role)
    channels/                     base.py (ChannelAdapter), mock_sms.py, inbound.py, registry.py
    pms/                          base.py (PmsAdapter), mock_pms.py, handle_event.py
    domain/                       one module per aggregate (see §4.1)
    queue/                        jobs.py, worker.py, handlers/
    realtime/                     ws.py (flask-sock route), presence.py, broadcast.py
    api/                          blueprints: auth, conversations, work_orders, quick_replies, assets,
                                  categories, users, departments, notifications, analytics, guests, hooks, dev
    errors.py                     exception classes + Flask error handlers
    cli.py                        `flask seed`, `flask worker` (standalone, for later)
  seed/                           seed.py + fixtures (deterministic)
  tests/                          pytest; conftest.py builds app + temp DB
  run.py                          dev entrypoint

web/                              Vite + React + TypeScript
  src/api/                        client.ts, types.generated.ts (from JSON Schema), hooks/, ws.ts
  src/auth/                       session context, role helpers, landing redirect
  src/components/ui/              button, input, dialog, dropdown, badge, avatar, toast
  src/features/inbox|board|analytics|notifications|admin|sim|login
  src/App.tsx, main.tsx, routes.tsx
  public/manifest.webmanifest
```

Tooling: `python -m venv .venv` + pip (`pip install -e "server[dev]"`), ruff, pytest. Web: npm, ESLint + Prettier, Vitest, Playwright for one E2E smoke suite. Dev: `npm run dev` runs Flask (`run.py`, port 5000, threaded, reloader) and Vite (port 5173, proxying `/api`, `/ws`, `/a`).

## 3. Data model

### 3.1 SQLAlchemy conventions

- Declarative 2.0 style (`Mapped[...]`, `mapped_column`). Table names snake_case exactly as below.
- `id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))`.
- Timestamps `DateTime(timezone=True)`, always UTC; every model has `created_at` (default now) and `updated_at` (default now, `onupdate` now).
- **Enums:** Python `enum.StrEnum` classes in `app/schemas/enums.py`, mapped with `sqlalchemy.Enum(..., native_enum=False, validate_strings=True)` → `VARCHAR` + CHECK constraint on SQLite; can switch to `native_enum=True` on Postgres. The same enum classes are used by Pydantic, so there is one definition.
- **JSON:** `sqlalchemy.JSON` → `TEXT` on SQLite, `JSON` on Postgres (`JSONB` via `.with_variant` later). Shapes validated by Pydantic models before write.
- `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000` set on every SQLite connection via an `engine` `connect` event; skipped when the URL is not SQLite.
- Migrations: Alembic, autogenerate reviewed by hand; `alembic upgrade head` is the only way a schema reaches a database (tests included).
- Every property-scoped model has `property_id` with an index, plus the composite indexes noted below. Foreign keys everywhere; soft-delete not used in Phase 1.

### 3.2 Tables

```
property
  id, name, code UNIQUE, timezone, address, phone, sms_number,
  brand, currency, logo_url, primary_color,
  settings JSON   -- {sla_minutes: 15, auto_resolve_hours: 4,
                  --  quiet_hours: {start:"21:00", end:"08:00"},
                  --  help_text: "..."}

user_account
  id, email UNIQUE, phone, first_name, last_name, avatar_url,
  locale DEFAULT 'en', status ENUM(active|disabled),
  password_hash, last_seen_at, notification_prefs JSON

property_membership
  id, user_id → user_account, property_id → property,
  role ENUM(agent|dept_staff|supervisor|manager|admin|corporate),
  department_id → department NULL,
  UNIQUE(user_id, property_id)

department
  id, property_id, name,
  type ENUM(front_desk|housekeeping|engineering|food_beverage|spa|security|valet|other),
  escalation_minutes INT, active BOOL

guest
  id, property_id, first_name, last_name, phone_e164,
  email, locale, loyalty_program, loyalty_tier, loyalty_number,
  vip BOOL, pms_profile_id,
  sms_consent_status ENUM(unknown|opted_in|opted_out),
  sms_consent_at, sms_consent_source, notes_summary
  UNIQUE(property_id, phone_e164)

stay
  id, guest_id, property_id, pms_reservation_id,
  room_number, room_type, rate_code,
  status ENUM(reserved|checked_in|checked_out|cancelled|no_show),
  arrival_date, departure_date, actual_checkin_at, actual_checkout_at,
  adults, children, group_code, market_segment,
  is_return_guest BOOL, stay_count INT, raw_pms JSON
  INDEX(property_id, status), INDEX(guest_id)

conversation
  id, property_id, guest_id, stay_id NULL,
  status ENUM(open|snoozed|archived),
  assigned_user_id NULL, assigned_department_id NULL,
  channel_primary ENUM(sms|web|whatsapp|email),
  last_guest_message_at, last_staff_message_at,
  first_response_seconds INT NULL,
  sla_due_at NULL, sla_breach_notified_at NULL,
  resolution_category_id NULL, snoozed_until NULL, archived_at NULL
  INDEX(property_id, status), INDEX(property_id, sla_due_at)

message
  id, conversation_id, property_id,
  direction ENUM(inbound|outbound),
  author_type ENUM(guest|staff|system|automation),
  author_user_id NULL,
  channel ENUM(sms|web|whatsapp|email),
  body, attachments JSON, digital_asset_id NULL,
  delivery_status ENUM(queued|sent|delivered|failed|undelivered),
  provider_message_id, provider_error_code, provider_error_message,
  redacted BOOL DEFAULT false, sent_at, delivered_at
  INDEX(conversation_id, sent_at), UNIQUE(property_id, provider_message_id)

internal_note
  id, conversation_id, property_id, author_user_id, body,
  mentions JSON   -- list of user ids
  -- NEVER joined into any guest-facing query. Separate table by design.

resolution_category
  id, property_id, name, parent_id NULL, active BOOL

work_order
  id, property_id, title, description,
  type ENUM(maintenance|housekeeping|guest_request|pm|other),
  priority ENUM(low|normal|high|urgent),
  status ENUM(open|assigned|in_progress|blocked|complete|verified|cancelled),
  location_type ENUM(room|public_area|equipment|other), location_ref,
  department_id NULL, assigned_user_id NULL,
  reported_by_user_id, source_conversation_id NULL, source_message_id NULL,
  attachments JSON, due_at, started_at, completed_at, verified_at,
  guest_notified_at NULL, acknowledged_at NULL
  INDEX(property_id, status), INDEX(source_conversation_id)

work_order_event
  id, work_order_id, property_id, user_id NULL,
  type ENUM(created|status_changed|assigned|commented|priority_changed),
  from_value, to_value, comment

draft_prompt
  id, property_id, conversation_id, work_order_id, body,
  status ENUM(pending|sent|dismissed), resolved_at, resolved_by_user_id
  -- the unsent, editable closed-loop message (design.md §6.4)

quick_reply
  id, property_id, department_id NULL, shortcut, title, body,
  category, locale, usage_count INT, active BOOL
  UNIQUE(property_id, shortcut)

digital_asset
  id, property_id, name, description, category,
  type ENUM(file|link|menu|map|form),
  url, short_code UNIQUE, thumbnail_url, department_id NULL,
  active BOOL, valid_from, valid_until, send_count INT

session
  id, user_id, token_hash UNIQUE, expires_at, ip, user_agent, last_seen_at

job
  id, type, payload JSON, run_at, attempts INT, max_attempts INT,
  status ENUM(queued|running|done|failed|dead),
  last_error, locked_at, finished_at
  INDEX(status, run_at)

notification
  id, property_id, user_id, type, title, body,
  entity_type, entity_id, read_at NULL
  INDEX(user_id, read_at)

audit_log
  id, property_id NULL, actor_user_id NULL, action,
  entity_type, entity_id, before JSON, after JSON, ip, user_agent
  -- append-only: the domain layer exposes only record(); no update/delete path

pms_event
  id, integration_key, external_id, event_type, payload JSON,
  processed_at, error
  UNIQUE(integration_key, external_id, event_type)
```

## 4. Backend

### 4.1 Domain layer

One module per aggregate in `app/domain/`. Every public function takes `(db: Session, property_id: str, ...)` and filters every query on `property_id`. Blueprints never touch models directly; they validate with Pydantic, call the domain, and serialise with Pydantic. Raw SQL (`text()`) is allowed only in `analytics` and must stay ANSI-portable (no SQLite-only functions) so it survives the Postgres move.

| Module | Responsibilities |
|---|---|
| `conversations` | list with filters (`all\|mine\|unassigned\|overdue\|resolved\|dept:<id>\|archived`), detail (messages + notes + open WOs + pending prompts), assign to user/department, archive (optional resolution category), unarchive, snooze/unsnooze, `find_or_create_for_guest`, `reopen_if_archived` |
| `messages` | `send()` — **the only outbound path** — `record_inbound()`, `retry()`, `update_delivery_status()` |
| `consent` | `apply_inbound_keywords()` (STOP family, START, HELP), `assert_can_send()`, `record_opt_in()` |
| `redaction` | card-number pattern + Luhn check → masked body, returns `(body, redacted)` |
| `notes` | create, list; mention extraction → notifications |
| `guests`, `stays` | upsert from PMS shape, in-house lookup by phone |
| `work_orders` | create (incl. `prefill_from_conversation`), `transition()` with `assert_transition()`, assign, comment, list/board, event log; on `→ complete` with `source_conversation_id` creates `draft_prompt` |
| `draft_prompts` | list pending for conversation, mark sent/dismissed |
| `quick_replies` | CRUD, search by shortcut/body, `interpolate(body, ctx)` for `{{guest_first_name}}`, `{{room_number}}`, `{{property_name}}`, `{{agent_first_name}}`, `{{departure_date}}` |
| `assets` | CRUD, short link resolution |
| `notifications` | create (+ broadcast), list, mark read, `notify_user_or_department()` |
| `analytics` | volume by day/hour, first-response p50/p90 (computed in Python from fetched durations), SLA breach count, per-agent table, WO by type/status/department, mean time to resolution |
| `audit` | `record()`; called by every mutation of guest data, messages, memberships, consent |
| `sms` | `segment_count(body)` — GSM-7 vs UCS-2 detection, 160/153 and 70/67 rules |

**Work order transitions** (`assert_transition`):

```
open        → assigned | in_progress | cancelled
assigned    → in_progress | open | cancelled
in_progress → blocked | complete | cancelled
blocked     → in_progress | cancelled
complete    → verified | in_progress   (reopen if inspection fails)
verified    → (terminal)
cancelled   → (terminal)
```

Assigning a user while `open` moves to `assigned`. `acknowledged_at` is set on the assignee's first view or first transition.

**Send path** (`messages.send(db, property_id, conversation_id, body, author_user_id, author_type, digital_asset_id=None, draft_prompt_id=None, allow_opt_out_confirmation=False)`):

1. Load conversation + guest. `consent.assert_can_send(guest)` raises `ConsentError` if `opted_out`, unless `allow_opt_out_confirmation` (used only for the STOP confirmation itself). Rejections are audit-logged with reason `CONSENT_OPTED_OUT` and create no message row.
2. Append asset short link if `digital_asset_id`; bump `send_count`.
3. Insert `message` with `delivery_status=queued`, `sent_at=now`.
4. Update conversation `last_staff_message_at`, clear `sla_due_at`, set `first_response_seconds` if null and a guest message exists.
5. If `draft_prompt_id`: mark prompt `sent`, set the work order's `guest_notified_at`.
6. `jobs.enqueue('outbound.send', {message_id})`.
7. Commit, then broadcast `message.created`. Return the message.

**Inbound path** (`channels/inbound.handle(db, property_id, from_, to, body, provider_message_id)`):

1. Idempotency: if `(property_id, provider_message_id)` exists, return the existing message.
2. `guests.find_or_create_by_phone`; if `sms_consent_status=unknown` → `opted_in`, source `inbound_sms`.
3. `stays.find_in_house_for_guest` → attach to conversation if found.
4. `conversations.find_or_create_for_guest` (reopens archived: `status=open`, `archived_at=None`).
5. `consent.apply_inbound_keywords(body)` — STOP family: set `opted_out`, send one confirmation via `messages.send(..., allow_opt_out_confirmation=True)`, still store the inbound. START family: `opted_in`. HELP: send help text. Keyword messages skip the SLA and notification steps.
6. `redaction.redact(body)`.
7. Insert `message(inbound, guest, delivered)`, set `last_guest_message_at`, `sla_due_at = now + sla_minutes`, `sla_breach_notified_at = None`.
8. `notifications.notify_user_or_department(assigned_user_id or assigned_department_id or front_desk)`.
9. Commit, then broadcast `conversation.created` or `conversation.updated`, and `message.created`.

Broadcasts always happen **after commit** so a client refetch sees the data.

### 4.2 Channel adapter

```python
class ChannelAdapter(Protocol):
    channel: Channel                     # Channel.sms
    supports_rich_media: bool
    max_length: int
    def send(self, to: str, body: str, *, message_id: str) -> SendResult: ...   # SendResult(provider_message_id)
    def verify_inbound(self, request: Request) -> bool: ...
    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage: ...  # from_, to, body, provider_message_id
```

`MockSmsAdapter`:
- `send()` returns `mock-<uuid>` immediately and enqueues `mock.delivery_status` jobs: `sent` at +0.4 s, `delivered` at +1.2 s. If `to` ends in `0000`, enqueues `failed` at +0.4 s with `provider_error_code='30007'`, message "Carrier violation (mock)".
- `verify_inbound` compares header `X-Mock-Secret` to `MOCK_SMS_SECRET` (default `dev`).
- `parse_inbound` reads `From`, `To`, `Body`, `MessageSid` — the Twilio field names — so the simulator posts Twilio-shaped form payloads and a future `TwilioAdapter` differs only in `verify_inbound`.

`channels/registry.get_adapter(channel)`; env `SMS_ADAPTER=mock` is the only value in Phase 1.

### 4.3 PMS adapter

```python
class PmsAdapter(Protocol):
    def start(self, on_event: Callable[[PmsEvent], None]) -> None: ...
    def stop(self) -> None: ...
    def fetch_in_house(self, property_id: str) -> list[NormalizedStay]: ...

@dataclass
class PmsEvent:
    external_id: str
    type: Literal['reservation.created', 'stay.checked_in', 'stay.checked_out', 'stay.room_changed']
    property_id: str
    stay: NormalizedStay
    guest: NormalizedGuest
    raw: dict
```

`MockPmsAdapter` is driven by the recurring `pms.tick` job (every `PMS_TICK_SECONDS`, default 90, `0` disables): picks a seeded `reserved` stay arriving today and checks it in, or a `checked_in` stay departing today and checks it out. Dev endpoints under `/api/dev/pms/` fire a specific event on demand. `pms/handle_event.py` upserts guest and stay, records `pms_event`, and is a no-op on duplicate `(integration_key, external_id, event_type)`.

### 4.4 Queue

`queue/jobs.py`: `enqueue(db, type, payload, run_at=None, max_attempts=5)`. `queue/worker.py`: `Worker(app, interval=0.5)` with `start()` (daemon thread) / `stop()` / `tick()` (one pass, used by tests). Each tick opens its own session, claims up to 20 jobs where `status='queued' AND run_at<=now` by setting `status='running', locked_at=now` in one transaction, then runs each handler in its own session. Success → `done`. Exception → `attempts+1`; if `attempts<max_attempts` → `queued` with `run_at = now + 2**attempts` seconds, else `dead`. `last_error` records `repr(exc)`. Jobs `running` for > 60 s are reclaimed at startup (crash recovery).

Started once by `create_app()` when `START_WORKER=1`; under the Werkzeug reloader only the child process (`WERKZEUG_RUN_MAIN == 'true'`) starts it.

Handlers (`queue/handlers/`):

| type | does |
|---|---|
| `outbound.send` | load message, call adapter, set `provider_message_id`; on adapter exception set `failed` + error, re-raise for retry |
| `mock.delivery_status` | apply a status transition to a message, broadcast `message.status_changed` |
| `sla.sweep` | recurring every 30 s: conversations with `sla_due_at < now AND sla_breach_notified_at IS NULL` → notification to assignee else department, set `sla_breach_notified_at`, broadcast `conversation.updated` |
| `snooze.wake` | recurring every 60 s: `snoozed` with `snoozed_until <= now` → `open` |
| `pms.tick` | recurring: drives `MockPmsAdapter` when enabled |

Recurring jobs re-enqueue themselves at the end of each run; `create_app()` seeds them if absent.

### 4.5 Realtime

`flask-sock` route at `/ws`. On connect, read the `sid` cookie and load the session; close with 4401 if invalid. Client sends `{"type":"subscribe","propertyId":...}`; server verifies membership and registers the socket under that property (close 4403 otherwise). A `ConnectionRegistry` (dict property_id → set of sockets, guarded by a `threading.Lock`) is the broadcast target; dead sockets are dropped on send failure.

Server → client events (`{"type", "propertyId", "payload", "at"}`):
`conversation.created` · `conversation.updated` · `message.created` · `message.status_changed` · `typing.update` · `presence.update` · `work_order.created` · `work_order.updated` · `draft_prompt.created` · `notification.created`

Client → server: `subscribe` · `presence` `{conversationId|null, state:'viewing'|'composing'}` · `heartbeat`.

`realtime/presence.py`: `dict[conversation_id, dict[user_id, PresenceEntry(state, seen_at, user)]]` with a lock. Heartbeat 5 s from clients; a sweeper thread every 5 s drops entries older than 10 s and broadcasts `presence.update` for changed conversations. `composing` is set when the composer gains focus (§6.1).

`realtime/broadcast.py: broadcast(property_id, type, payload)` is a plain function the domain layer and worker call — no pub/sub layer. **Production note:** run with one worker process (`gunicorn -k gthread -w 1 --threads 16`) because presence and the connection registry are in-memory.

### 4.6 Auth and authorisation

- `POST /api/auth/login {email, password}` → `bcrypt.checkpw` (cost 12) → insert `session` (32 random bytes, stored as SHA-256 hex) → `Set-Cookie: sid=<token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200`.
- `POST /api/auth/logout`, `GET /api/auth/me` → user + memberships.
- `@require_auth`: loads session by hash, rejects expired → 401. Touches `last_seen_at` at most once per minute. Sets `g.user`.
- `@require_property`: reads `<property_id>` from the URL, loads `property_membership` for `(user, property)`; none → **403**. Sets `g.property_id`, `g.membership`.
- `@require_role(*roles)` and `@require_capability(cap)` → 403. Capability map in `app/auth/permissions.py` mirrors `design.md` §3.2 for Phase 1: `view_all_conversations`, `reply`, `assign`, `add_note`, `archive`, `create_work_order`, `close_work_order`, `view_property_analytics`, `view_own_stats`, `manage_admin`. `dept_staff` conversation lists are filtered to their department or themselves.
- Rate limit (in-memory, per IP, sliding window): login 10/min; webhooks 60/min.

### 4.7 API

All staff routes live under `/api/p/<property_id>/` and pass `require_auth → require_property`. Bodies and responses are Pydantic models; responses are built with `model_dump(by_alias=True)` in camelCase.

```
POST   /api/auth/login | logout          GET /api/auth/me

GET    conversations?filter=&dept=&cursor=&limit=
GET    conversations/<id>                  → conversation, guest, stay, messages, notes, workOrders, draftPrompts
POST   conversations/<id>/messages         {body, digitalAssetId?, draftPromptId?}
POST   conversations/<id>/messages/<mid>/retry
POST   conversations/<id>/notes            {body}
PATCH  conversations/<id>                  {assignedUserId?|assignedDepartmentId?|status?|resolutionCategoryId?|snoozedUntil?}
POST   conversations/<id>/draft-prompts/<pid>/dismiss

GET    work-orders?status=&type=&dept=&assignee=&mine=
POST   work-orders                         {..., sourceConversationId?, sourceMessageId?}
GET    work-orders/prefill?conversationId= → suggested title/description/location/department
GET    work-orders/<id>
PATCH  work-orders/<id>                    {status?|assignedUserId?|departmentId?|priority?|comment?}

GET    quick-replies?q=      POST/PATCH/DELETE quick-replies[/<id>]
GET    assets                POST/PATCH/DELETE assets[/<id>]
GET    resolution-categories POST/PATCH/DELETE resolution-categories[/<id>]
GET    users                 POST/PATCH users[/<id>]     (memberships managed here)
GET    departments
GET    notifications?unread=   POST notifications/<id>/read   POST notifications/read-all
GET    analytics/overview?from=&to=
GET    analytics/agents?from=&to=
GET    guests/<id>

POST   /api/hooks/sms/inbound              form-encoded, Twilio field names; adapter.verify_inbound
GET    /a/<short_code>                     302 to asset url

# dev only (FLASK_ENV != production)
POST   /api/dev/pms/check-in/<stay_id> | check-out/<stay_id>
GET    /api/dev/sim/guests                 seeded guests + phones for the simulator
GET    /api/dev/sim/thread?phone=          outbound+inbound messages as the guest sees them
```

Errors: `{"error": {"code", "message", "details"?}}`. Pydantic `ValidationError` → 400; `ConsentError` → 422 `CONSENT_OPTED_OUT`; `TransitionError` → 409; `NotFound` → 404; auth → 401/403.

Response models use `model_config = ConfigDict(extra='forbid')`. `ConversationDetail` is the staff shape; `GuestThread` (used by `/api/dev/sim/thread` and later by the guest surface) has no field that could carry a note.

### 4.8 Type generation for the frontend

`python -m app.schemas.export_json_schema > web/src/api/schema.json` writes one JSON Schema document with all request/response models under `$defs`. `npm run gen:types` in `web/` runs `json-schema-to-typescript` to produce `src/api/types.generated.ts`. Both are committed; a test in `server/tests/test_schema_export.py` fails if the export is stale.

## 5. Frontend

### 5.0 Visual direction — "Night Shift" (chosen 2026-09-10)

Approved mockups live in `docs/mockups/*.dc.html` (published canvas: https://claude.ai/code/artifact/cc54191d-cdf8-4474-b5a2-eda523b54ad8). The web build reproduces them:

- **Themes:** dark is the default; light is a per-user toggle in the nav ("Theme"), persisted in `notification_prefs.theme` and defaulting to the device `prefers-color-scheme`. Both palettes are the token sets in the `renderVals()` block of any `docs/mockups/*.dc.html` (keys `bg, bg2, nav, surface, surface2, border, border2, border3, text, text2, text3, text4, accent, accentText, roomNum, sel, outBg, outText, autoBg, autoText, autoBorder, noteBg, noteBorder, noteText, noteIcon, okBg, okText, okBorder, okBtn, okBtnText, okBanner, warnBg, warnText, dangerBg, dangerText, danger, presenceBg, presenceText, presenceAv, avMuted, avText, tagBg, tagText, timerDoneBg, timerDoneText`). They become CSS custom properties on `:root` / `[data-theme="light"]` and Tailwind colours via `var()`.
- **Type:** Space Grotesk (UI) + JetBrains Mono (room numbers, timers, ids, counts), both from Google Fonts with system fallbacks.
- **Shape language:** 184 px labelled left nav; 44 px controls (`.btn`), 8–10 px radii, 1 px borders, no shadows; amber `accent` for primary actions and the selected-row inset bar; SLA shown as a mono countdown timer chip (green / amber / red backgrounds); status colours reserved (green ok, amber warn, red danger) and never used decoratively.
- **Screens covered by mockups:** Inbox (`Main`), Board, WorkOrder, Analytics, Admin (quick replies; other admin screens reuse the table + edit-panel pattern), Simulator, Mobile (department-staff task list). Login and Notification centre follow the same tokens without a dedicated mockup.
- **Charts:** single-hue amber bars with direct labels; red only for past-SLA; no chart library.

### 5.1 Stack and conventions

Vite · React 18 · TypeScript strict · Tailwind · TanStack Query · React Router v6. Types come from `types.generated.ts` (§4.8). No component library; `components/ui/` holds ~8 small primitives. Server state only in TanStack Query; UI state in component/context. One `useRealtime()` hook owns the native `WebSocket`, reconnects with backoff, invalidates queries by event type, and exposes presence/typing maps.

### 5.2 Routes and screens

| Route | Screen | Notes |
|---|---|---|
| `/login` | Login | Redirects to role landing after success |
| `/app` | Landing redirect | agent → inbox; dept_staff, supervisor → board?mine=1; manager, admin, corporate → analytics |
| `/app/inbox`, `/app/inbox/:id` | Inbox | Three columns ≥1024 px; two ≥768; one below with back nav |
| `/app/board`, `/app/work-orders/:id` | Board / WO detail | Kanban by status + list toggle; detail with timeline and transition buttons that reflect `assert_transition` |
| `/app/analytics` | Analytics | Date range; cards + tables; no charting lib (bars are CSS) |
| `/app/notifications` | Notification centre | Also a bell + unread badge in nav |
| `/app/admin/users`, `/quick-replies`, `/assets`, `/categories` | Admin CRUD | Admin only |
| `/sim` | Phone simulator | Dev only; excluded from the production build |

Nav shows only items the role may use. Guest context panel shows guest, stay, consent status, open work orders, pending prompts, recent notes.

### 5.3 Inbox behaviour

- Queue sorted oldest-unanswered first. Row: unread state, assignee avatar, SLA chip (green → amber at 66 % → red past due), channel icon, presence avatars of others viewing.
- Conversation header shows "Marcus is viewing" / "Marcus is replying" from presence.
- Composer: `/` opens quick-reply palette filtered by shortcut and body; Enter inserts interpolated text. Asset picker appends short link. Segment counter shows `N chars · M segments`. Ctrl/Cmd+Enter sends.
- Optimistic send: message appears as `queued`, updates via `message.status_changed`; `failed` shows the error and a Retry button hitting `/retry`.
- **Create work order** button opens a modal pre-filled from `/work-orders/prefill`; on save the WO appears in the context panel.
- Pending `draft_prompt` renders as a banner above the composer: "Work order #204 (AC repair, 412) is complete. Let Sarah know?" with **Use draft** (loads body into composer, passes `draftPromptId` on send) and **Dismiss**.
- Internal notes render in-thread visually distinct (amber, "Internal") and come from a separate array in the response.
- Archive prompts for an optional resolution category. Resolved and Archived are separate filters. **Resolved** is computed at query time, never stored: open, answered (last staff message after the last guest message), no guest message for `auto_resolve_hours`, and no open linked work order — so an ignored guest can never fall out of the queue, and any new inbound message returns the conversation to the live list automatically.
- Opted-out guests show a red consent chip; the composer stays enabled (the server enforces) but shows a warning.

### 5.4 Simulator

Left: pick a seeded guest or enter a phone. Centre: a phone frame rendering the guest's thread (hotel messages as received bubbles with delivery status). Bottom: text input that POSTs Twilio-shaped form data `From, To, Body, MessageSid` to `/api/hooks/sms/inbound` with the `X-Mock-Secret` header. Quick buttons: `STOP`, `HELP`, "AC broken in my room", a card-number sample (to demo redaction).

## 6. Compliance behaviours (design.md §9.1)

- STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT (case-insensitive, trimmed of whitespace and trailing punctuation, and matching the **whole message**) → `opted_out`, `sms_consent_at`, source `sms_keyword`; exactly one confirmation ("You're unsubscribed from <property> messages. Reply START to resume."). START/UNSTOP/YES → `opted_in`, matched the same whole-message way.
  (Amended during Task 10: the original rule said "alone or first word", which unsubscribes a guest who writes
  "Stop by room 400 later" and opts in one who writes "Yes, extra towels please". Whole-message matching is the
  CTIA/carrier convention and avoids both misfires.)
- HELP → `property.settings.help_text`.
- Send path rejects `opted_out` with `CONSENT_OPTED_OUT` except the confirmation itself. The rejection creates no `message` row; it audit-logs the attempt.
- Card numbers: sequences of 13–19 digits allowing spaces/dashes that pass Luhn → replaced with `**** **** **** 1234` before storage, `redacted=true`; the UI shows a "Card number redacted" chip.
- `audit_log` rows for: login/logout, consent changes, message send/reject, note create, conversation assign/archive, WO create/transition, membership changes, admin CRUD.

## 7. Testing

**Server (pytest + Flask test client).** `tests/conftest.py`: once per session, create a template SQLite file and run `alembic upgrade head` on it; per test module, copy it to a fresh temp file, build the app with `create_app(TestConfig)` pointing at it, and load a small fixture (2 properties, departments, 4 users across roles, 3 guests, stays). Time is injected via `app.clock` (a callable returning `now`) so tests can advance it; the worker is driven with `worker.tick()`. Fixtures provide `login_as(email)` returning a client with the cookie set.

| §11.1 | Test |
|---|---|
| 1 | Inbound from unknown number → 200; conversation exists, guest created, `opted_in`, visible in `GET conversations` |
| 2 | Inbound from a phone matching an in-house stay → conversation has `stay_id`, detail includes room number |
| 4 | Send to a `…0000` number → after `worker.tick()` twice, message is `failed` with `30007`; `POST …/retry` re-queues |
| 5 | Inbound `STOP` → guest `opted_out`, exactly one outbound confirmation; subsequent `POST messages` → 422 `CONSENT_OPTED_OUT`, audit row exists, no message row |
| 6 | `GET work-orders/prefill` returns room, guest, last inbound body, suggested department; `POST work-orders` stores `source_conversation_id` |
| 7 | Transition to `complete` → one `draft_prompt(pending)` for the conversation; `message` count unchanged |
| 8 | Inbound at T; advance clock 15 min; `sla.sweep` → conversation in `filter=overdue`; notification row for assignee (or department members) |
| 9 | Enumerate every rule in `app.url_map` whose path starts with `/api/p/<property_id>`; for each method, a user with membership only at A requests it for B → 403 (bodies may be empty; 403 must precede validation). New routes are covered automatically. |
| 10 | `GuestThread` has `extra='forbid'`; test inserts a note then asserts the guest-thread payload validates and contains no note body anywhere (deep string search) |

Also: `assert_transition` matrix, `segment_count`, `interpolate`, `redact` (positive, Luhn-negative, false-positive phone numbers), job retry/backoff/dead-letter, snooze wake, PMS idempotency, dept_staff list filtering, stale schema export.

**Web (Vitest + Testing Library).** Segment counter, quick-reply palette filtering, SLA chip thresholds, transition button enablement.

**E2E (Playwright).** One smoke: simulator sends text → agent logs in → sees conversation → replies → status reaches `delivered` in simulator → creates WO → engineer logs in (second context) → completes → agent sees draft prompt → sends → simulator shows message. A second spec opens the same conversation in two contexts and asserts each sees the other's presence within 2 s (§11.1 #3).

## 8. Seed data (design.md §11.2)

`flask seed` (or `npm run seed`) deletes `server/data/app.db`, runs `alembic upgrade head`, then inserts:

- **Property A** "Harbourview Hotel" (code `HVH`, tz `America/New_York`, sms `+15550100`), settings `sla_minutes=15`, `auto_resolve_hours=4`.
- **Property B** "Lakeside Inn" (`LSI`) with 1 admin, 1 agent, 3 guests, 2 conversations — for isolation tests and to show property switching.
- Departments A: Front Desk, Housekeeping, Engineering.
- 12 staff at A: 3 agents, 2 housekeeping staff, 2 engineers, 1 HK supervisor, 1 chief engineer (supervisor), 1 duty manager, 1 admin (also GM), 1 corporate. All passwords `Password123!`; emails `<first>@hvh.test`. Listed in README.
- Rooms: numbers 101–120 … 601–620 used across stays.
- 85 `checked_in` stays today with varied loyalty tiers, 10 `reserved` arriving today, 10 departing today (for the mock PMS to act on), 8 `checked_out` yesterday.
- 30 conversations: ~8 unassigned and fresh, ~6 assigned and answered, ~5 overdue, ~4 snoozed/resolved-eligible, ~5 archived with categories, 2 with a pending draft prompt, 1 opted-out guest, 1 with a redacted card message. Message timestamps spread over the past 3 days.
- 15 open work orders across types/priorities/statuses, 6 linked to conversations.
- ~15 quick replies (`/wifi`, `/checkout`, `/towels`, `/late`, `/parking`, …), 8 assets (WiFi card, map, breakfast menu, …), resolution category tree (Maintenance > HVAC/Plumbing/Electrical, Service > Housekeeping delay/Front desk, Billing, Praise, Question > Hours/Amenities).
- Recurring jobs seeded.

Seed is deterministic (`random.Random(42)`) so screenshots and tests are stable.

## 9. Configuration

`server/.env`: `FLASK_ENV=development`, `PORT=5000`, `DATABASE_URL=sqlite:///data/app.db`, `SESSION_SECRET`, `MOCK_SMS_SECRET=dev`, `SMS_ADAPTER=mock`, `PMS_TICK_SECONDS=90`, `START_WORKER=1`, `CORS_ORIGIN=http://localhost:5173`. Web: `VITE_API_BASE` (empty in dev; Vite proxies).

## 10. Acceptance for this build

Done when: the README's setup (`python -m venv`, `pip install -e "server[dev]"`, `npm install`, `npm run seed`, `npm run dev`) brings up both surfaces on a clean machine; all server tests including the §11.1 suite pass; the Playwright smoke passes; every screen in §5.2 is reachable by the roles that should see it and hidden from the ones that shouldn't; README documents setup, seeded credentials, the simulator, and the Postgres switch below.

## 11. Moving to PostgreSQL later

Designed to be a configuration change:

1. `pip install psycopg[binary]`; set `DATABASE_URL=postgresql+psycopg://…`.
2. `alembic upgrade head` — the existing migrations run unchanged because they use portable types (`Enum(native_enum=False)`, `JSON`, `DateTime(timezone=True)`). Optionally add a migration that switches enums to native and JSON to `JSONB`.
3. The SQLite PRAGMA hook is skipped automatically for non-SQLite URLs.
4. The analytics `text()` statements are written portably and are the only SQL to re-check.
5. With Postgres in place, presence/broadcast can move to `LISTEN/NOTIFY` if you ever need more than one worker process.

Nothing in the domain, API, queue, realtime, or web packages references SQLite.
