# Task 4 Report: Authentication

## What was implemented

Implemented exactly the file set from the brief, in step order:

- `server/app/auth/__init__.py` (empty)
- `server/app/auth/passwords.py` — `hash_password`, `verify_password` (bcrypt)
- `server/app/auth/sessions.py` — `create_session`, `load_session`, `touch_session`, `revoke_session`, `COOKIE_NAME`, `SESSION_HOURS`
- `server/app/auth/permissions.py` — `CAPABILITIES` map, `has_capability`
- `server/app/auth/decorators.py` — `require_auth`, `require_property`, `require_role`, `require_capability`
- `server/app/ratelimit.py` — `RateLimiter`, `rate_limited`, `login_limiter`, `webhook_limiter`
- `server/app/schemas/common.py` — `CamelModel`
- `server/app/schemas/auth.py` — `LoginRequest`, `UserOut`, `MembershipOut`, `SessionOut`
- `server/app/api/_util.py` — `db_session`, `parse_body`, `parse_query`, `serialize`, `ok`, `no_content`, `client_meta`
- `server/app/domain/__init__.py` (empty), `server/app/domain/audit.py` — `audit.record` (sole writer of `audit_log`)
- `server/app/api/auth.py` — `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
- `server/tests/test_auth.py` — the 9 tests from the brief, verbatim

Modified:
- `server/app/__init__.py` — registers `auth.bp` alongside `health.bp`
- `server/tests/fixtures.py` — `_hash` now calls `app.auth.passwords.hash_password(pw, rounds=4)` instead of raw `bcrypt`
- `server/tests/conftest.py` — resets `login_limiter`/`webhook_limiter` in the `app` fixture before `create_app`; also sets `email_validator.TEST_ENVIRONMENT = True` at module load (see Deviation below)
- `server/pyproject.toml` — `"pydantic>=2.9"` → `"pydantic[email]>=2.9"`

All code bodies match the brief verbatim (passwords.py, sessions.py, permissions.py, ratelimit.py, schemas/common.py, schemas/auth.py, api/_util.py, domain/audit.py, auth/decorators.py, api/auth.py, and the `login()` function's two-session failure-audit structure).

## Deviation from the brief (flagging per instructions)

**Problem:** `pip install -e ".[dev]"` with `pydantic[email]>=2.9` pulled in `email-validator==2.3.0`. Since email-validator 2.x, `validate_email` rejects RFC 2606 reserved TLDs (`test`, `invalid`, `localhost`, `local`, `onion`, `arpa`) as "special-use" domains by default. All fixture users use `*.test` emails (e.g. `agent@hvh.test`), and Pydantic's `EmailStr` calls `email_validator.validate_email` internally with only `check_deliverability=False` hard-coded — there is no way to pass `allow_special_use_domain`/`test_environment=True` through `EmailStr` itself. Every login attempt with `.test` fixture emails was rejected with `VALIDATION_FAILED` before I could even test/exercise real login logic.

**Fix:** `email-validator` ships a module-level global switch for exactly this (`email_validator.TEST_ENVIRONMENT`, default `False`). I set it to `True` once at the top of `server/tests/conftest.py` (test process only — never touched in `app/` production code), with a one-line comment explaining why. This does not touch `check_deliverability` (already off) and does not change production request validation, since the flag is only ever set inside the test conftest module.

I judged this in-scope to fix myself (rather than reporting NEEDS_CONTEXT) because: it's the library's own documented escape hatch for this exact scenario (its name is literally `TEST_ENVIRONMENT`), it's a one-line, fully-reversible, test-only change, and without it none of the 9 new tests — nor the brief's own `LoginRequest`/`EmailStr` design — could work with the existing fixture data. Flagging here per "Self-Review" instructions in case the task author wants a different approach (e.g. pinning an older `email-validator`, or changing fixture emails to non-reserved domains).

## Tests and results

### TDD evidence

**RED** — `python -m pytest tests/test_auth.py -q` (after writing `server/tests/test_auth.py`, before any `app/auth`/`app/api/auth.py` code existed):
```
FAILED tests/test_auth.py::test_login_sets_cookie_and_me_returns_memberships
FAILED tests/test_auth.py::test_login_rejects_bad_password_and_unknown_email
FAILED tests/test_auth.py::test_login_validates_body - assert 404 == 400
FAILED tests/test_auth.py::test_me_requires_session - AssertionError: ...
FAILED tests/test_auth.py::test_logout_revokes_session - AssertionError: ...
FAILED tests/test_auth.py::test_expired_session_is_rejected - AssertionError: ...
FAILED tests/test_auth.py::test_login_is_rate_limited - assert 404 == 429
FAILED tests/test_auth.py::test_login_and_logout_are_audited - AssertionError: ...
FAILED tests/test_auth.py::test_disabled_user_cannot_login - assert 404 == 401
9 failed in 0.60s
```
All failures were 404s (route `/api/auth/login` did not exist yet) — expected, since no blueprint was registered.

**GREEN** — after implementing all files and fixing the `email_validator.TEST_ENVIRONMENT` issue, `python -m pytest -q`:
```
.....................                                                    [100%]
21 passed in 1.63s
```
Confirmed again with `python -m pytest -q -W error` (forces any warning to be a hard error): `21 passed in 1.54s`.

Verbose run confirms distribution: `tests/test_auth.py` 9 passed, `test_errors.py` 1, `test_fixtures.py` 3, `test_health.py` 2, `test_models.py` 6 = 21 total (12 pre-existing + 9 new), matching the task-level expectation. Note: brief step 13 says "18 passed" — that count is stale relative to what's actually on disk (12 pre-existing + 9 new = 21); I did not adjust tests to match the brief's stale number, per instructions.

## Files changed

Created:
- `server/app/auth/__init__.py`
- `server/app/auth/passwords.py`
- `server/app/auth/sessions.py`
- `server/app/auth/permissions.py`
- `server/app/auth/decorators.py`
- `server/app/ratelimit.py`
- `server/app/schemas/common.py`
- `server/app/schemas/auth.py`
- `server/app/api/_util.py`
- `server/app/api/auth.py`
- `server/app/domain/__init__.py`
- `server/app/domain/audit.py`
- `server/tests/test_auth.py`

Modified:
- `server/app/__init__.py`
- `server/tests/fixtures.py`
- `server/tests/conftest.py`
- `server/pyproject.toml`

## Self-review findings

- Completeness: all 9 new tests pass and each exercises real behavior (cookie flags, `me` payload shape/camelCase, bad password vs unknown email vs disabled user all returning 401/UNAUTHORIZED, body validation returning 400/VALIDATION_FAILED, logout revoking the session row, session expiry via `clock.advance`, rate limiting via the real `RateLimiter`, and audit rows read back from the DB via `AuditLog`) — no mocks used anywhere.
- Discipline: every file's contents match the brief verbatim; no extra functions, no speculative config. `git diff` on modified files (`app/__init__.py`, `pyproject.toml`, `tests/conftest.py`, `tests/fixtures.py`) shows only the exact lines the brief specifies, plus the one documented `email_validator.TEST_ENVIRONMENT` line.
- Rate-limit test dependency verified: `login_limiter.reset()` / `webhook_limiter.reset()` run inside the `app` fixture before each test's `create_app`, so the 10-hits-then-429 test is isolated from other tests.
- Expiry test dependency verified: `load_session` compares `s.expires_at <= clock.now()`, and `clock.advance(hours=13)` in the test mutates the same frozen clock `load_session` reads, so the session correctly appears expired.
- `git status` before commit showed `CLAUDE.md` as modified (pre-existing, unrelated to this task, not created by me this session) — left untouched and unstaged; only `git add server` was staged, matching the brief's commit step exactly.
- Ran `ruff check app tests`: pre-existing files (`app/db.py`, `app/clock.py`, `app/models/*.py`, `tests/test_models.py`, some existing lines in `tests/fixtures.py`) already had lint findings (UP017, UP035, E501, I001) predating this task — left untouched per "surgical changes." My new files also produce a few `E501`/`UP035`/`UP047` findings, but only because their content is verbatim from the brief (e.g. long lines in `app/api/auth.py`, `app/auth/permissions.py`, `app/api/_util.py`, `tests/test_auth.py`); I did not reformat brief-mandated code to satisfy ruff, since the brief's exact text was required. No linter run was requested as a success criterion — noting for visibility, not as a blocker.

## Concerns

- The `email_validator.TEST_ENVIRONMENT = True` addition to `tests/conftest.py` is a deviation from the brief's literal "reset limiters" instruction for that file — necessary because the currently-installed `email-validator` version rejects `.test` fixture emails through `EmailStr` otherwise. See "Deviation" section above for full reasoning; happy to switch to an alternative (e.g., changing fixture emails, or pinning `email-validator<2.0`) if preferred.
- Ruff reports some pre-existing style debt across the codebase (not introduced by this task) plus a handful of line-length/type-hint findings in the new files that come directly from the brief's verbatim code blocks.

## Pydantic version installed

`pydantic==2.13.5` (with `email-validator==2.3.0` pulled in via the `[email]` extra).
