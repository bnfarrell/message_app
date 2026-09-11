# Final fix wave — whole-branch review findings

Base: `58877de` (232 tests). Head after this wave: `c84490f`. **247 tests passing, 0 warnings,
`ruff check .` clean.**

Six commits, one per concern:

| SHA | Subject |
|---|---|
| `c1f0da4` | security(server): scope StaffPatch to per-property fields |
| `7f323f4` | fix(server): scope the pms_event idempotency key by property |
| `56342ad` | fix(server): production hardening must fail closed, not open |
| `7e60a6e` | fix(server): stop guest identity leaving through unscoped routes |
| `da840d3` | fix(server): write a stay's status and its check-in timestamp together |
| `c84490f` | test(server): guard the consent gate against a direct Message write |

No ruling was wrong. One workflow consequence of narrowing `StaffPatch` is flagged under
"Concerns" — it is a real gap, but not a reason to keep the hole.

---

## 1. CRITICAL — cross-tenant account takeover (`c1f0da4`)

### What changed

`app/schemas/users.py` — `StaffPatch` now carries **only** `role` and `department_id`.
`password`, `status`, `first_name` and `last_name` are gone. The model has a docstring stating
why: `UserAccount` is global, one account may hold memberships at several properties, and an
endpoint authorised by a membership at the property in the URL must never write global columns.

`app/domain/users.py` — `update_staff` writes only the membership. The `UserAccount` load, the
`hash_password` call, the `status`/`first_name`/`last_name` branches and the `password_reset` key
in the audit `after` payload are gone with them (they were orphaned by this change, not
pre-existing dead code). Audit behaviour for what remains is unchanged: `membership.updated` with
`before`/`after` on `role` and `department_id`. `CamelModel` is `extra="forbid"`, so a request
that still sends `password` or `status` is now a 400 `VALIDATION_FAILED` rather than silently
ignored — the removal is enforced at the edge, not just unread.

The last-admin guard is in the same file: `ADMIN_ROLES` is derived from the capability map
(`[r for r in Role if has_capability(r, "manage_admin")]`, so it tracks `permissions.py` rather
than hardcoding `{admin, corporate}`), and `_assert_not_last_admin` raises `Conflict` (409) when
the membership being demoted or deleted is the last one at that property holding the capability.
It is called from both `update_staff` (with the incoming role, so an admin→corporate move is
allowed) and `remove_membership`.

### The test on the escalation axis

`tests/test_users_admin.py::test_property_admin_cannot_take_over_an_account` mirrors the
reproduction exactly: admin at A adds `regional@group.test` (a manager at B only) to A by email —
still 201, the feature stands — then attempts the password reset and the status disable, and
finally asserts the attacker's password does not log in and the victim still holds `{HVH, LSI}`.
Every request in it is to Property A's own URL, which is why the existing suite's
"request Property B's URL, expect 403" shape structurally cannot reach it.

**Verified against the pre-fix code** by stashing only `app/schemas/users.py` and
`app/domain/users.py` and rerunning that one test:

```
>       assert pwned.status_code == 400, "a property-scoped PATCH reset a global password"
E       AssertionError: a property-scoped PATCH reset a global password
E       assert 200 == 400
```

Three more tests were added alongside it:

- `test_staff_patch_rejects_every_global_account_field` — loops all four removed fields, so a
  partial restoration of any one of them fails.
- `test_last_admin_cannot_be_demoted_or_removed` — Property B has exactly one `manage_admin`
  membership; demote → 409, delete → 409; after a second admin is created, both succeed.
- `test_last_admin_guard_counts_corporate_and_allows_admin_to_admin_moves` — Property A has an
  admin *and* a corporate member; the guard counts both, permits admin→corporate, and still
  refuses the last one standing.

### Existing tests updated, and why that is not weakening them

Only one: `test_admin_creates_updates_and_removes_staff`. It asserted that
`PATCH {"status": "disabled"}` returned `disabled` and that the user could then no longer log in.
Both assertions encoded the vulnerability as the contract — "a property admin can disable a global
account" is the denial-of-service half of the same defect. Rewriting them to accept a 400 would
have been the weakening move; instead the test now exercises the **replacement** workflow and
asserts the stronger property: deleting the membership returns 204, and the account afterwards
still logs in successfully but comes back with `memberships == []`. That is a sharper assertion
than the original (it pins *both* that property access is gone *and* that the global account
survived), and it is the behaviour a per-property admin should actually have.

No other test referenced the removed fields.

---

## 2. IMPORTANT — `pms_event` idempotency key was global (`7f323f4`)

`app/models/infra.py` — `PmsEvent` gains
`property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)`
and the unique constraint becomes
`("property_id", "integration_key", "external_id", "event_type")`, with a class docstring tying it
to `Stay`'s `(property_id, pms_reservation_id)` uniqueness.
`app/pms/handle_event.py` — the dedup `SELECT` and the `PmsEventRow(...)` insert both carry
`event.property_id`; the docstring is updated to name the new key.

### Migration `0003_pms_event_property_scope.py`

Follows `0002`'s conventions: module docstring, `revision = "0003"`, `down_revision = "0002"`,
`render_as_batch` is already on in `alembic/env.py` so `batch_alter_table` handles SQLite.
Upgrade adds the column, swaps the unique constraint, creates `ix_pms_event_property_id` and the
FK to `property`. Downgrade is symmetric: drops FK, index and column and restores the three-column
constraint.

`op.execute("DELETE FROM pms_event")` runs first. `pms_event` is a pure idempotency ledger —
nothing references its rows, and an existing row carries no property to backfill from (the raw
payload shape is adapter-specific). The only consequence is that a PMS replaying a
pre-migration event would be processed once more. That is documented in the migration docstring.

### Upgrade-from-empty verification

Ran `run_migrations()` against a fresh empty SQLite file (the same call
`tests/conftest.py::template_db_path` uses to build the session template) and inspected the result:

```
cols:    [... 'property_id']
uniques: [{'name': 'uq_pms_event_idem',
           'column_names': ['property_id','integration_key','external_id','event_type']}]
indexes: [{'name': 'ix_pms_event_property_id', 'column_names': ['property_id'], 'unique': 0}]
fks:     [{'name': 'fk_pms_event_property_id', 'constrained_columns': ['property_id'],
           'referred_table': 'property', 'referred_columns': ['id']}]
```

Round-trip verified separately — `upgrade head` → `downgrade 0002` → `upgrade head`:

```
after downgrade cols: [... no property_id]
after downgrade uq:   ['integration_key','external_id','event_type']
after downgrade fks:  []
re-upgrade uq:        ['property_id','integration_key','external_id','event_type']
```

The whole 247-test suite then passes, which is the real proof: every test builds its database from
that migrated template.

### Test

`tests/test_pms.py::test_same_external_id_in_two_properties_is_processed_twice` sends reservation
`R-1001` to Property A and then to Property B, asserts both return `True`, asserts two `Stay` rows
exist with the right `(property_id, room_number)` pairs and two `pms_event` rows with distinct
`property_id`, and finally re-sends A's event to confirm the key is *still* idempotent within a
property. Verified against pre-fix code (stashing the model, handler and migration):

```
E  AssertionError: Property B's event was swallowed as a duplicate
E  assert False is True
```

---

## 3. IMPORTANT — production hardening failed open (`56342ad`)

**Dev endpoints.** `Config` gains `ENABLE_DEV_ENDPOINTS: bool = False` and a
`dev_endpoints_enabled` property = `ENABLE_DEV_ENDPOINTS and not is_production`. `create_app`
registers the dev blueprint on that. It is belt and braces on purpose: the positive opt-in is what
the finding asked for, and the `not is_production` term preserves Task 21's stronger guarantee
that the blueprint is never even constructed in production. `run.py` and `dev_start.py`
`os.environ.setdefault("ENABLE_DEV_ENDPOINTS", "1")` so the one-click local flow and the React
simulator keep working; because of the second term, that `setdefault` cannot re-open the hole if
someone points a dev entrypoint at a production config.

**Cookie.** `SESSION_COOKIE_SECURE: bool | None = None` plus a `cookie_secure` property: `None`
means "secure in production, not in development"; `1`/`0` forces either way (HTTPS tunnel in dev,
plain-HTTP staging). `app/api/auth.py` reads `current_app.config["APP"].cookie_secure` instead of
the hardcoded `secure=False`.

**Session secret.** `INSECURE_SESSION_SECRETS` in `config.py` holds both the dataclass default
(`"dev-secret-change-me"`) and the value shipped in `.env.example`
(`"change-me-in-production"`) — a copied-and-forgotten `.env` contains the latter, so checking only
the dataclass default would have left the likelier case open. `create_app` raises `RuntimeError`
before doing anything else when `is_production` and the secret is one of those.

**Splitting the worker off the production flag.** Moving dev endpoints onto their own switch
already separates "data exposure" from "job delivery". But the worker gate's `is_production` term
was never really about production — it was a proxy for "no reloader parent process exists", and it
left the other half of the finding live: a gunicorn deployment with `START_WORKER=1` that forgot
`FLASK_ENV=production` silently started **no** worker and delivered nothing. So the gate now asks
a switch that means what it says: `Config.USE_RELOADER`, set by the two entrypoints that actually
pass `debug=True`, and the guard reads
`config.START_WORKER and (under_reloader or not config.USE_RELOADER)` at both the worker and the
presence sweeper. `run.py` / `dev_start.py` now pass `debug=cfg.USE_RELOADER`, so the value that
decides whether a reloader exists is the same value the guard consults, instead of two
independently-derived ones. Under gunicorn, `USE_RELOADER` is unset and the worker starts whenever
`START_WORKER=1`, regardless of `FLASK_ENV`.

**Docs.** `.env.example` gains `ENABLE_DEV_ENDPOINTS=1`, `USE_RELOADER=0` and a commented
`SESSION_COOKIE_SECURE`, each with a comment saying what the unsafe state is. `README.md` gains a
"Configuration switches that matter" section covering all three plus the production
`SESSION_SECRET` refusal.

### Tests

- `test_dev.py::test_dev_routes_absent_unless_explicitly_enabled` — builds an app with a **default**
  `Config` (asserting `ENV == "development"`, i.e. the exact forgotten-env-var state) and requires
  `/api/dev/sim/guests` → 404. This is the test the old code could not have passed.
- `test_dev.py::test_dev_routes_absent_in_production` — retained, now built with
  `ENABLE_DEV_ENDPOINTS=True` so it proves the production term independently of the opt-in.
- `test_auth.py::test_session_cookie_is_secure_in_production_and_configurable` — pins the
  `cookie_secure` truth table and asserts the live `Set-Cookie` header carries `Secure` when
  configured, so the route is genuinely reading the config.
- `test_auth.py::test_production_refuses_to_boot_with_the_placeholder_session_secret` — loops the
  whole `INSECURE_SESSION_SECRETS` set, so adding a placeholder to the set without wiring it up
  fails.
- `test_queue.py::test_start_worker_guard_avoids_duplicate_start_under_reloader` — **updated**.
  Its three original cases are preserved verbatim in meaning (production/no reloader → starts;
  dev parent → does not; dev child → starts), re-expressed against `USE_RELOADER`, and a **fourth**
  case is added: no reloader, `FLASK_ENV` forgotten → still starts. That fourth case is the
  regression the split exists to prevent. `tests/conftest.py` sets `ENABLE_DEV_ENDPOINTS=True`
  (with a comment), since `test_dev.py` exercises those routes.

---

## 4. IMPORTANT — guest data leaving through unscoped routes (`7e60a6e`)

The ruling was followed exactly, including its narrowness.

**Work-order list and mutation: untouched.** No viewer scoping was added to `work_orders.list`,
to `PATCH`, or to the assignment/transition/priority paths.

**`work_orders.detail`.** Now takes `*, viewer_role, viewer_user_id, viewer_department_id` as
**required** keyword arguments — deliberately not optional-with-defaults, so a new caller cannot
fail open by forgetting them (the compiler catches it, not a reviewer). A small
`_can_see_conversation` helper wraps `conversations.assert_viewer_can_see` in a `try/except
Forbidden`, and `guest_name` / the conversation-derived `room_number` are computed only when it
returns `True`. `room_number` still falls back to `wo.location_ref`, which is the work order's own
column and stays visible. Both call sites in `app/api/work_orders.py` (GET and the PATCH response)
pass the viewer.

**`GET /api/p/<id>/guests/<guest_id>`.** Gains `@require_capability("view_all_conversations")`,
with a docstring saying why that is the right capability: the payload (phone, consent status, stay
history, conversation ids) is strictly more than a `dept_staff` member can assemble through the
conversation routes, and `view_all_conversations` is the capability `dept_staff` correctly lacks.

### Tests — `tests/test_guest_data_leakage.py` (new file, 3 tests)

- `test_work_order_detail_hides_conversation_derived_guest_fields` — reproduces the live probe: a
  conversation assigned to Housekeeping, a work order raised from it, and an Engineering
  `dept_staff` viewer. Asserts 403 on the conversation, **200** on the work order (the ruling: the
  visibility stands), `guestName is None`, `roomNumber == "412"` from `locationRef`, a successful
  **mutation** whose response also omits the field, and that an agent still sees `"Sarah Chen"`.
- `test_work_order_detail_shows_guest_fields_to_the_assigned_department` — the anti-over-correction
  guard: housekeeping staff *can* see the conversation, so they must still get the guest name and
  the stay's room number.
- `test_guest_detail_requires_view_all_conversations` — `dept_staff` 403s; agent, supervisor,
  manager, admin and corporate all still get 200 with the phone number.

### Existing tests updated

- `test_work_orders.py::test_detail_renders_event_timeline` — call-site only, now passes an agent
  viewer. No assertion changed.
- `test_work_orders_api.py::test_prefill_create_transition_and_detail_via_api` — asserted
  `d["guestName"] == "Sarah Chen"` for the **engineer**, who is 403'd from that (unassigned)
  conversation. That assertion *was* the leak. It is replaced by the pair `guestName is None` for
  the engineer and `== "Sarah Chen"` for the agent, with a comment. Net coverage went up: the
  file now pins both sides of the rule where it previously pinned only the leaking one.

---

## 5. IMPORTANT — static guard on the consent gate (`c84490f`)

`tests/test_isolation.py::test_only_the_messages_domain_constructs_a_message`, alongside the
existing `conversations.get(` guard.

**The rule:** no module under `app/` except `app/domain/messages.py` may construct a `Message` at
all. The blanket form is deliberate and the docstring says so — a rule phrased as "no *outbound*
`Message`" would match a spelling of the `direction` argument rather than the invariant, which is
precisely the known weakness of the `conversations.get(` guard it sits next to; any new call site
can be argued into looking inbound. "Nobody but the consent gate builds the row" is checkable and
cannot be argued with.

**Implementation:** `ast.parse` per file, not regex. It resolves the local names actually bound to
the model in each module (`from app.models import Message`, `... as M`,
`from app.models.conversations import Message`) and flags calls to any of them, **plus** any
attribute call spelled `<anything>.Message(...)`.

**What it catches** (verified by planting a violating module at
`app/queue/handlers/_planted.py` using *both* evasive spellings and running the test):

```
E  AssertionError: only app/domain/messages.py may construct a Message: it is the sole consent
   gate; call messages.send()/record_inbound() instead:
   ['app/queue/handlers/_planted.py:6', 'app/queue/handlers/_planted.py:7']
```

- a direct `Message(...)` anywhere under `app/`, at any nesting depth, in any new subpackage
  (`rglob`), including inside a function, comprehension or lambda;
- an aliased import (`from app.models import Message as M; M(...)`);
- a module-qualified call (`from app import models; models.Message(...)`);
- multi-line and oddly-formatted constructions, which a regex would miss.

**What it does not catch**, stated in the docstring rather than left for the next reader to
discover:

- construction through indirection — `cls = Message; cls(...)`, `getattr(models, "Message")(...)`,
  anything resolved at runtime;
- a SQLAlchemy Core `insert(Message)`, `bulk_save_objects`, or raw SQL;
- flipping an existing row's `direction` after the fact (`m.direction = Direction.outbound`);
- anything outside `app/` — `seed/seed.py` and `tests/factories.py` build `Message` rows directly
  on purpose, and neither ships a text to a real guest.

None of those are *accidental* bypasses, which is the failure mode the guard exists for. A
companion test, `test_the_message_constructor_guard_is_not_vacuous`, points the same helper at
`app/domain/messages.py` and requires it to find at least two constructions, so the guard cannot
silently stop working (e.g. if the model were re-exported from a path the import matcher misses).

---

## 6. IMPORTANT — the write that creates a bad NULL (`da840d3`)

**The write.** `handle_event`'s attribute loop copies `status` straight off the event, so keying
`actual_checkin_at` off `event.type` alone left a stay with `status=checked_in` and a NULL
timestamp whenever the status arrived on some other event type. The check-out branch now sets only
the status, and status/timestamp consistency is enforced afterwards against the *resulting* status
rather than the event type: a `checked_in` or `checked_out` stay always gets an
`actual_checkin_at`, and a `checked_out` stay always gets an `actual_checkout_at`. Existing
check-in/check-out behaviour is unchanged (`test_check_in_upserts_guest_and_stay` and
`test_check_out_updates_existing_stay_and_does_not_reopen_consent` pass untouched).

**The bonus ordering fix.** `app/domain/stays.py:15` is now
`.order_by(Stay.actual_checkin_at.desc().nulls_last(), Stay.id.desc())`, with a comment. **Only
that one site** — the six-site sweep stays deferred to the PostgreSQL switch as instructed.

**Tests.** `test_status_and_check_in_timestamp_are_written_together` drives a `stay.room_changed`
event carrying `status=checked_in` and asserts the timestamp is set; verified failing pre-fix
(`where None = <Stay>.actual_checkin_at`). `test_in_house_lookup_prefers_a_stay_with_a_real_check_in_time`
inserts a NULL-timestamp "ghost" stay in room 999 alongside the real 412 and asserts the lookup
still returns 412 — belt and braces for the ordering itself.

---

## Out of scope — confirmed untouched

The synchronous WebSocket send in `app/realtime/registry.py`; the six-site `.nulls_last()` sweep
(only `stays.py:15`, as the bonus allowed); the N+1 in `conversations.list`; a broader effect-side
isolation suite; the ruff pass and formatting.

---

## Verification

```
$ ../.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 29%]
........................................................................ [ 58%]
........................................................................ [ 87%]
...............................                                          [100%]
247 passed in 17.69s

$ ../.venv/Scripts/python.exe -m ruff check .
All checks passed!
```

232 → 247: **15 tests added**, 0 removed, 4 updated (all four documented above with the reason the
update is a strengthening rather than a weakening).

`web/src/api/schema.json` was regenerated after the `StaffPatch` change
(`python -m app.schemas.export_json_schema`) and committed in `c1f0da4`; a second run after all
remaining work produced no diff, confirming nothing later touched a Pydantic model.
`tests/test_schema_export.py` passes. `server/data/*.db` was never staged; the tree is clean.

---

## Concerns

**1. Password reset now has no in-app path at all.** Narrowing `StaffPatch` was right, and
revoking property access has a proper replacement (`DELETE` on the membership, which the updated
test now pins). But an admin could previously reset a forgotten password, and nothing replaces
that: `create_staff` sets a password only when it creates a *new* account, and there is no
self-serve reset flow in Phase 1. A staff member who forgets their password is now stuck without
direct database access.

This is not a reason to keep the hole — resetting a *global* credential from a property-scoped URL
is the vulnerability, not the feature. The correct replacement is a route that is not
property-scoped: either self-serve ("email me a reset link", which needs an email channel Phase 1
does not have) or an account-level admin surface outside `/api/p/<property_id>/`. Neither was in
this fix wave's scope and I did not invent one. **Flagging it as a known Phase 1 gap that should be
on the list before real staff use the system.**

**2. `email_validator.TEST_ENVIRONMENT` is still gated on `not is_production`**
(`app/__init__.py:16`), which is the same "permissive by default, one forgotten env var away"
shape as the dev-blueprint bug — it was simply not in the finding list. The blast radius is
genuinely small (it only permits RFC 2606 reserved domains like `hvh.test` to pass email
validation; no data is exposed) and it is load-bearing for the seeded demo accounts, so I left it
alone rather than widening the diff. Worth a one-line move onto `dev_endpoints_enabled` at some
point.

**3. Migration `0003` deletes the `pms_event` ledger.** Documented in the migration and above.
Correct for a pre-release system with no property to backfill from; if any deployment already has
a meaningful ledger, the operator should know that a PMS replaying a pre-migration event will be
processed a second time.
