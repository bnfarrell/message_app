# Task 9 Report: Channel adapter interface, MockSmsAdapter, outbound send and delivery-status handlers

## What was implemented

All code written exactly as specified in the brief (verbatim), with one call-site addition to `create_app`:

- `server/app/channels/__init__.py` — empty.
- `server/app/channels/base.py` — `SendResult`, `InboundMessage` dataclasses and the `ChannelAdapter` Protocol.
- `server/app/channels/mock_sms.py` — `MockSmsAdapter`: `send()` enqueues `mock.delivery_status` jobs (sent+delivered at +400ms/+1200ms, or a single failed at +400ms for numbers ending in `0000`, error code `30007`); `verify_inbound()` checks `X-Mock-Secret` via `hmac.compare_digest`; `parse_inbound()` reads Twilio-style field names (`From`/`To`/`Body`/`MessageSid`).
- `server/app/channels/registry.py` — `build_sms_adapter()`, `install()` (stores adapter on `app.extensions["sms_adapter"]`), `get_sms_adapter()`.
- `server/app/__init__.py` — added `from app.channels import registry as channel_registry; channel_registry.install(app, config)` immediately after `app.extensions["db"] = Database(...)`, per the brief's instruction. This is the only change to a pre-existing file.
- `server/app/schemas/conversations.py` (new) — `MessageOut` (message shapes only; conversation shapes deferred to Task 11).
- `server/app/domain/messages.py` (new) — `update_delivery_status()` and `retry()` (the delivery-status half; `send`/`record_inbound` deferred to Task 11, not stubbed).
- `server/app/queue/handlers/outbound.py` (new) — `outbound.send` handler: loads the message/conversation/guest, calls the adapter, stores `provider_message_id`; on adapter exception marks the message failed and re-raises so the job retries; idempotent no-op if the message is no longer `queued`.
- `server/app/queue/handlers/mock_delivery.py` (new) — `mock.delivery_status` handler: applies a status transition only if it moves the state machine forward (`queued→sent→delivered`, or `queued/sent→failed`), and no-ops if the message's `provider_message_id` was cleared by a retry (stale job from a superseded send).
- `server/tests/factories.py` (new) — `make_conversation`, `make_message`.
- `server/tests/test_mock_sms.py` (new) — the five tests specified in the brief.

No deviations from the brief were made; no brief defects were found.

## What was tested and the results

Focused test file: `tests/test_mock_sms.py` — 5 tests, all passing.
Full suite: `pytest -q` — 69 passed (64 prior + 5 new), 0 warnings, output pristine.

## TDD Evidence

**RED**

Command: `../.venv/Scripts/python.exe -m pytest tests/test_mock_sms.py -q`

Output (before any implementation files existed, only `tests/factories.py` and `tests/test_mock_sms.py` written):

```
=================================== ERRORS ====================================
___________________ ERROR collecting tests/test_mock_sms.py ___________________
ImportError while importing test module '...\tests\test_mock_sms.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
...
tests\test_mock_sms.py:1: in <module>
    from app.channels.mock_sms import MockSmsAdapter
E   ModuleNotFoundError: No module named 'app.channels'
=========================== short test summary info ===========================
ERROR tests/test_mock_sms.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.20s
```

This matches the brief's expected failure exactly (`ModuleNotFoundError: app.channels`) — the module did not exist yet.

**GREEN**

Command: `../.venv/Scripts/python.exe -m pytest tests/test_mock_sms.py -q`

Output (after implementing all Step 3-5 files):

```
.....                                                                    [100%]
5 passed in 0.88s
```

Command: `../.venv/Scripts/python.exe -m pytest -q` (full suite)

Output:

```
.....................................................................    [100%]
69 passed in 4.37s
```

No warnings in either run.

## Files changed

- `server/app/__init__.py` (modified — 4 lines added: import + `channel_registry.install(app, config)` call)
- `server/app/channels/__init__.py` (new, empty)
- `server/app/channels/base.py` (new)
- `server/app/channels/mock_sms.py` (new)
- `server/app/channels/registry.py` (new)
- `server/app/domain/messages.py` (new)
- `server/app/queue/handlers/outbound.py` (new)
- `server/app/queue/handlers/mock_delivery.py` (new)
- `server/app/schemas/conversations.py` (new)
- `server/tests/factories.py` (new)
- `server/tests/test_mock_sms.py` (new)

Not committed: `docs/superpowers/RESUME.md`, which was already modified in the working tree before this task began (unrelated to this work) — left untouched, and excluded from the commit per instructions to commit `server` only.

## Self-review findings

- Verified every produced file matches the brief's code verbatim (adapter, registry, handlers, domain, schema, factories, tests) — no unauthorized edits.
- Verified the single non-brief-verbatim change (`app/__init__.py`) is minimal: two new lines plus a blank line, placed exactly where the brief specifies ("right after the database is registered"), touching nothing else.
- Ran `ruff check` over all new/changed files. Findings are all long-line (E501) and one unused-import (F401 `select` in `outbound.py`) issues, and every one of them is in code copied verbatim from the brief — per project convention ("ruff style findings in plan-verbatim code are NOT fixed per-task"), these are left for the Task 24 pass. `app/__init__.py` (the one file I authored beyond brief-verbatim code) has no ruff findings.
- Confirmed `app/channels/__init__.py` is truly empty (0 bytes) as the brief specifies.
- Confirmed no stray files were staged/committed (`git status` after `git add server` showed exactly the 11 intended paths; `docs/superpowers/RESUME.md` was left unstaged).
- Confirmed TDD was followed: tests and factories were written and run to RED before any implementation code existed, matching the brief's specified failure mode exactly.

## Issues or concerns

None. No brief defects encountered; all five specified tests passed as written, the full suite is green with pristine output, and the diff is a clean, surgical, brief-verbatim implementation plus the one prescribed call-site edit.

---

## Fix round 1/5 (review findings)

The tree had moved on since the original commit (`8b967f1`, 91 tests) — Task 10 (guests/stays/consent) and a Task 8 fix had landed. Read the current state of all four affected files before editing; nothing had changed shape underneath this task's code.

### Finding 1 — provider exception never persisted (fixed per ruling)

`server/app/queue/handlers/outbound.py`: the `except Exception` branch now marks the message `failed` via `messages.update_delivery_status(...)` and returns normally, instead of re-raising. `Database.session()` (`app/db.py:68-74`) rolls back on any exception escaping the `with` block, so the prior re-raise discarded the "mark failed" write along with everything else, leaving the message stuck at `queued` once the job's attempts ran out (`dead`, invisible to staff). Per the controller's ruling, no second-session/relaxed-guard machinery was added — the accepted trade-off is no automatic backoff retry for transient provider errors; recovery is the visible `failed` state plus the existing `messages.retry()`. The stale comment ("mark failed, then re-raise so the job retries") was rewritten to explain the actual behavior and why.

### Finding 2 — forward-only guard moved into the domain (fixed per ruling)

`server/app/domain/messages.py`: `update_delivery_status` now holds the forward-only invariant itself. A new module-level `_FORWARD_ORDER = [queued, sent, delivered]` list is checked at the top of the function; if both the current and target status are in that list and the target's index is `<=` the current status's index, the function returns the message unchanged — no field writes, no `db.flush()`, no `queue_event`. `failed`/`undelivered` remain outside `_FORWARD_ORDER`, so `queued -> failed` (and any transition into a terminal error state) is unaffected, matching the controller's verification that `retry()` (which sets `queued` directly on the model, not through this function) and `queued -> failed` both still work.

`server/app/queue/handlers/mock_delivery.py` was simplified per the ruling: the duplicate ordering check (`order = [...]`, the `<=` comparison) was removed since the invariant now lives in the domain function. Only the adapter-specific guard remains: if `msg.provider_message_id is None`, the message was reset by a retry after this job was scheduled, so the stale job is a no-op.

### Tests added

1. `test_provider_exception_marks_failed_without_retry` — monkeypatches `MockSmsAdapter.send` to raise `RuntimeError("boom")`, runs `worker.tick()`, and asserts the message ends up `failed` with `provider_error_code == "ADAPTER_ERROR"`, `"boom"` in `provider_error_message`, and exactly one `message.status_changed` event with `deliveryStatus == "failed"`.

   **Verified this test fails against the pre-fix handler**: I temporarily restored the old (committed, re-raising) `outbound.py` via `git show HEAD:server/app/queue/handlers/outbound.py`, ran the test in isolation, and it failed exactly as the reviewer described — the message was still `queued` (`AssertionError: assert <DeliveryStatus.queued> == <DeliveryStatus.failed>`). I then restored the fixed handler and confirmed the test passes.

2. `test_update_delivery_status_ignores_backward_transition` — calls `update_delivery_status` directly to move a message to `delivered`, clears the captured `events` list, then calls it again with `sent`; asserts the returned message and the persisted row are still `delivered`, and that no new `message.status_changed` event was queued.

### Ruff

Ran `ruff check` on the four changed files. One newly authored comment line in `mock_delivery.py` exceeded 100 chars (E501) and was rewritten to fit — this is new code, not brief-verbatim, so it was fixed rather than deferred. The pre-existing `F401 sqlalchemy.select imported but unused` in `outbound.py` is brief-verbatim (present since the original task-9 commit, untouched by this fix) and is left for the Task 24 ruff pass per project convention.

### Covering tests run

Command: `../.venv/Scripts/python.exe -m pytest tests/test_mock_sms.py -q`

```
.......                                                                  [100%]
7 passed in 1.03s
```

Command (full suite): `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 77%]
.....................                                                    [100%]
93 passed in 4.52s
```

(A second full-suite run after the ruff line-length tweak also passed: 93 passed, no warnings.)

### Files changed (fix round)

- `server/app/domain/messages.py` — forward-only guard added to `update_delivery_status`.
- `server/app/queue/handlers/mock_delivery.py` — duplicate ordering check removed; comment rewritten.
- `server/app/queue/handlers/outbound.py` — no re-raise on adapter exception; comment rewritten.
- `server/tests/test_mock_sms.py` — two new tests added.

### Commit

`c03f6be` — `fix(server): persist adapter failures without a discarded re-raise; enforce forward-only delivery status in the domain`

### Concerns

None. Both findings were genuine defects in the brief's own code (as the controller had already determined), the rulings were applied exactly as written, and no scope beyond the two findings plus their covering tests was touched.
