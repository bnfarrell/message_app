# Task 11 Report: Conversations domain, the send path, the inbound path, and the SMS webhook

## What I implemented

Followed the brief's steps in order, verbatim where specified:

1. **`server/tests/factories.py`** — added the `inbound(client, fx, from_phone, body, to=None, sid=None)` helper (brief-verbatim).
2. **`server/tests/test_inbound.py`** (new) — 10 tests covering: unknown-number guest+conversation creation (§11.1 #1), in-house stay attachment (§11.1 #2), conversation reuse, archived-conversation reopening, provider-SID idempotency, STOP opt-out + confirmation + blocked sends + START re-enable (§11.1 #5), HELP reply, card redaction on inbound bodies, webhook auth/404 rejection, and front-desk notification fan-out.
3. **`server/tests/test_send.py`** (new) — 4 tests covering: `send()` queuing a message, clearing SLA, and recording first-response time; the `reply` capability gate via the API; first-response recorded only once; and over-length rejection.
4. **`server/app/schemas/conversations.py`** — added `GuestOut`, `StayOut`, `ConversationSummary`, `SendMessageRequest` (kept existing `MessageOut`). Consolidated imports at the top of the file rather than mid-file (brief gave them as two separate append blocks; I merged them into one clean import block since that's not brief-verbatim content, just import placement).
5. **`server/app/domain/conversations.py`** (new) — `get`, `_setting`, `sla_minutes`, `auto_resolve_hours`, `find_or_create_for_guest` (reopens archived, converts snoozed, returns `(Conversation, created)`), `touch_updated`. Brief-verbatim.
6. **`server/app/domain/messages.py`** — appended `send()` (the consent-enforced outbound path: validates length, checks/audits opted-out rejections, applies digital-asset short-link, records first-response time once, resolves a pending draft prompt, enqueues `outbound.send`, audits `message.sent`, broadcasts `message.created`, touches the conversation) and `record_inbound()` (redacts card numbers, sets `last_guest_message_at`, starts the SLA clock unless `start_sla=False` for keyword messages, broadcasts `message.created`). Brief-verbatim; only reformatted the combined `app.schemas.enums` import line to multi-line to fit the project's 100-col ruff limit, since that specific import line was of my own construction (the brief gave it as two separate partial import lists to merge).
7. **`server/app/channels/inbound.py`** (new) — `InboundResult`, `property_for_number`, `handle()`: idempotent on provider SID, finds/creates the guest (opts them in if consent is `unknown`), finds an in-house stay, finds/creates the conversation, classifies the keyword, records the inbound message (suppressing SLA start for keyword messages), and branches on STOP/START/HELP/none — the last case notifying front desk. Brief-verbatim.
8. **`server/app/api/hooks.py`** (new) — `POST /api/hooks/sms/inbound`: rate-limited, verifies the shared secret, parses the Twilio-shaped form payload, resolves the property by `To` number (404 if none), calls `inbound.handle`, returns 204. Brief-verbatim.
9. **`server/app/api/conversations.py`** (new) — minimal blueprint: `POST /api/p/<property_id>/conversations/<conversation_id>/messages`, gated by `require_auth` → `require_property` → `require_capability("reply")`, calling `messages.send`. Brief-verbatim.
10. **`server/app/__init__.py`** — registered the two new blueprints (`conversations.bp`, `hooks.bp`).

## What I tested and the results

Full suite: `../.venv/Scripts/python.exe -m pytest -q` → **116 passed**, 0 warnings (was 102 before this task; +14 new tests).

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_inbound.py tests/test_send.py -q` (run immediately after writing the tests and the `factories.inbound` helper, before touching any implementation file):

```
FAILED tests/test_inbound.py::test_unknown_number_creates_guest_and_conversation
FAILED tests/test_inbound.py::test_known_in_house_guest_attaches_stay
FAILED tests/test_inbound.py::test_second_message_reuses_open_conversation
FAILED tests/test_inbound.py::test_archived_conversation_reopens_on_inbound
FAILED tests/test_inbound.py::test_duplicate_provider_sid_is_idempotent
FAILED tests/test_inbound.py::test_stop_opts_out_sends_one_confirmation_and_blocks_sends
FAILED tests/test_inbound.py::test_help_replies_with_property_help_text
FAILED tests/test_inbound.py::test_card_numbers_are_redacted_before_storage
FAILED tests/test_inbound.py::test_webhook_rejects_bad_secret_and_unknown_property_number
FAILED tests/test_inbound.py::test_inbound_notifies_front_desk_when_unassigned
FAILED tests/test_send.py::test_send_queues_message_clears_sla_and_records_first_response
FAILED tests/test_send.py::test_send_via_api_requires_reply_capability
FAILED tests/test_send.py::test_first_response_is_recorded_only_once
FAILED tests/test_send.py::test_send_rejects_over_length
14 failed in 1.19s
```
Failure reasons matched expectations exactly: the inbound-webhook tests failed with `404 NOT FOUND` (route not yet registered — `test_send_via_api_requires_reply_capability` failed with `assert 404 == 403` because the conversations blueprint didn't exist yet either), and every test that called `messages.send(...)` directly failed with `AttributeError: module 'app.domain.messages' has no attribute 'send'`. This is exactly the brief's predicted RED evidence ("404 on the webhook, `ImportError`/`AttributeError` for `messages.send`").

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_inbound.py tests/test_send.py -q`
```
..............                                                           [100%]
14 passed in 14.66s
```
Then the full suite: `../.venv/Scripts/python.exe -m pytest -q`
```
........................................................................ [ 62%]
............................................                             [100%]
116 passed in 4.31s
```
(A second full run after the one import-formatting cleanup below reconfirmed 116 passed in 34.63s, 0 warnings.)

## Files changed

- Modified: `server/app/__init__.py`, `server/app/domain/messages.py`, `server/app/schemas/conversations.py`, `server/tests/factories.py`
- Created: `server/app/domain/conversations.py`, `server/app/channels/inbound.py`, `server/app/api/hooks.py`, `server/app/api/conversations.py`, `server/tests/test_inbound.py`, `server/tests/test_send.py`

## Self-review findings

- Ran `ruff check` over every touched/created file. All remaining findings (long lines, one unused-import in `test_send.py`) trace directly to text copied verbatim from the brief, so left untouched per the project convention (one `ruff check --fix` pass at Task 24). The one finding that was *not* brief-verbatim — a combined `app.schemas.enums` import line in `messages.py` that I constructed myself while merging the brief's two separate "add these imports" snippets — I reformatted to ruff's suggested multi-line form, since that specific line's shape was my own choice, not the brief's text.
- Verified the isolation suite (`test_isolation.py`) still passes with the new `/api/p/<property_id>/conversations/<conversation_id>/messages` route auto-discovered: cross-property member gets 403 before the dummy conversation ID is ever looked up (decorator order: `require_auth` → `require_property` → `require_capability`), and the property-A admin is not blocked on their own property.
- Confirmed the consent short-circuit in `messages.send`: the audit row for a rejected opted-out send is written in a separate DB session (`get_db().session()`) precisely because the caller's session, which has written nothing yet, rolls back when `ConsentError` propagates — verified this produces exactly one audit row per rejected attempt and no `message` row, matching the STOP test's assertions.
- Confirmed the single `conversation.created` event (not also `conversation.updated`) fires for a brand-new inbound message with no keyword, because `handle()` queues its own event and never calls `messages.send` (which would otherwise call `conv_domain.touch_updated` and add a second event) on the non-keyword path.
- No unused imports, no dead code introduced beyond what the brief specifies. No behavior added beyond the brief's scope (no work on `ConversationDetail`/`NoteOut`/list-and-assign endpoints, which are explicitly Task 12).

## Issues or concerns

None. No brief defects found — every test passed as specified with no need to alter assertions or add exceptions. The full 116-test suite is green with pristine (warning-free) output.

---

## Fix report — round 1 (review findings)

Tree had moved on to `d870b63` (Task 12 landed: conversation list/detail/patch, notes, guest-thread shapes; suite at 127 tests) by the time this round started. All three findings were in `server/app/domain/messages.py`'s `send()`, which Task 12 did not touch.

### Finding 1 (Important) — nested audit session could deadlock

**Root cause:** `send()` opened a second `get_db().session()` to write the `message.rejected_opted_out` audit row while the caller's own session (`db`) was still open and possibly dirty. This is only safe when the caller's transaction has written nothing yet — true for today's one caller, but `inbound.handle` already flushes a guest/conversation/message before any `send()` call, and any future caller with a dirty session (e.g. Task 13's work-order guest notifications) would contend for the same SQLite write lock, block for `busy_timeout` (5s), then raise `OperationalError` — a 500 instead of a 422, and no audit row.

**Fix:**
- `app/errors.py`: `ConsentError.__init__` now accepts an optional `audit_write: Callable[[Session], None] | None` and stores it as `self.audit_write`.
- `app/domain/consent.py`: `assert_can_send()` gained the same `audit_write` parameter and forwards it into the `ConsentError` it raises (still the single call site, per the module docstring).
- `app/domain/messages.py`: `send()` no longer writes the audit row itself. It builds a small `_audit_rejection(audit_db)` closure (capturing `property_id`, `author_user_id`, `conv.id`, body length, `ip`, `user_agent`) and passes it to `consent.assert_can_send(..., audit_write=_audit_rejection)`. The `get_db`/`app.db` import is gone from `messages.py` — no import trace to it remains.
- `app/db.py`: `Database.session()`'s exception path now does `db.rollback()` (releasing whatever write lock the caller held), then, if the propagating exception carries an `audit_write` attribute, opens a brand-new `SessionLocal()` and runs the callback on it before committing and re-raising the original exception. This fires identically whether the caller reached here through a Flask request (`db_session()`) or a direct `database.session()` call in a test — no Flask app context or request is required, which is also why the covering test below needs neither.

This means the write now always lands after the caller's transaction has already ended, on a connection nothing else holds a lock on — regardless of what the caller had flushed.

**Covering test:** `tests/test_send.py::test_send_audit_survives_a_dirty_caller_session` — opens a `database.session()`, flushes a guest consent-status change, a new conversation, and an inbound message on that same session (mimicking `inbound.handle`'s dirty transaction), then calls `messages.send(...)` targeting the now-opted-out guest with no confirmation. Asserts the propagated `ConsentError` has `.status == 422` / `.code == "CONSENT_OPTED_OUT"`, that no outbound `Message` row was created, and that the `message.rejected_opted_out` `AuditLog` row exists once the session has fully unwound.

Against the pre-fix code this test failed with `RuntimeError: Working outside of application context` (the nested `get_db().session()` call requires a live Flask app context that a direct domain-level caller — exactly the shape of a future dirty-session caller — does not have), which is an even more direct demonstration of the bug's fragility than the deadlock itself.

### Finding 2 (Minor, promoted) — short link appended after the length check

**Root cause:** `MAX_BODY` was enforced before the digital-asset short link (`" /a/{short_code}"`) was appended, so a max-length body plus the link could ship over both `MAX_BODY` and the mock adapter's own 1600-char `max_length`.

**Fix:** moved the `if len(body) > MAX_BODY: raise ValidationFailed(...)` check to after the `digital_asset_id` block, so it now measures the final body including any appended link.

**Covering test:** `tests/test_send.py::test_send_rejects_when_digital_asset_link_pushes_body_over_length` — creates a `DigitalAsset` with `short_code="spa1"`, sends a body of `MAX_BODY - 5` characters (passes the old check) with that asset attached; the appended `" /a/spa1"` (8 chars) pushes the final body to 1603, over `MAX_BODY`. Failed with "DID NOT RAISE ValidationFailed" against the pre-fix code; passes now.

### Finding 3 (Minor, promoted) — SLA clear not guarded by author type

**Root cause:** `conv.sla_due_at = None` and `conv.sla_breach_notified_at = None` ran for every `author_type`, while `first_response_seconds` (two lines below) was correctly guarded to `AuthorType.staff` only. No live effect yet (system sends only happen on the STOP/START/HELP branches, where `record_inbound` never started an SLA), but the first automated send in a later task would silently satisfy an SLA no human ever answered.

**Fix:** wrapped both `sla_due_at`/`sla_breach_notified_at` clearing and the `first_response_seconds` computation in one `if author_type == AuthorType.staff:` block (removing the now-redundant inline `author_type == AuthorType.staff` clause from the `first_response_seconds` condition, since it's covered by the outer guard). `conv.last_staff_message_at = now` was left unconditional — the finding did not flag it, and the brief's original code set it unconditionally too.

**Covering test:** `tests/test_send.py::test_system_send_does_not_clear_sla_or_record_first_response` — sends an inbound message (starts the SLA), then calls `messages.send(..., author_type=AuthorType.system)`; asserts `sla_due_at` is still set and `first_response_seconds` is still `None` afterward. Failed with `assert None is not None` against the pre-fix code; passes now.

### Incidental cleanup

Removing the manual opted-out `if` block in `send()` left `SmsConsentStatus` and the `app.db.get_db` import unused in `app/domain/messages.py`; both were removed (they trace directly to this fix, not to unrelated pre-existing code). Reflowed the `app.schemas.enums` import back to one line now that it fits.

### Tests run

Focused: `../.venv/Scripts/python.exe -m pytest tests/test_send.py tests/test_inbound.py -q`
```
.................                                                        [100%]
17 passed in 1.39s
```

Full suite: `../.venv/Scripts/python.exe -m pytest -q`
```
........................................................................ [ 55%]
..........................................................               [100%]
130 passed in 7.67s
```
(Re-ran the full suite five times over the course of this fix round while iterating: 4.90s, 4.42s, 7.62s, 7.07s, 7.67s across runs — all 130 passed, 0 warnings each time. Pasting these as they actually came out, per the note about timing coherence: wall-clock time for this suite on this machine visibly varies run to run, sometimes by close to 2x, with no code change in between.)

`ruff check` was run over every file touched in this round (`app/db.py`, `app/errors.py`, `app/domain/consent.py`, `app/domain/messages.py`, `tests/test_send.py`). Two findings traced to code written in this round (an unused `SmsConsentStatus` import and one over-length line in the new `_audit_rejection` closure) were fixed. All remaining findings in those files are pre-existing lines untouched by this round (line-length findings in `_get`/`update_delivery_status`/the pre-existing `audit.record` call at the end of `send()`, the module docstring in `consent.py`, and the project-wide `typing.Callable`-vs-`collections.abc.Callable` (UP035) style choice already used identically in `app/queue/handlers/__init__.py` and `app/realtime/broadcast.py`) — left alone per the project's one-`ruff --fix`-pass-at-Task-24 convention.

### Files changed (this round)

`server/app/db.py`, `server/app/errors.py`, `server/app/domain/consent.py`, `server/app/domain/messages.py`, `server/tests/test_send.py`.
