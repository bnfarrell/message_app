# Task 1 Report: Project scaffold, config, app factory, health route

## What I implemented

Followed the brief step-by-step, verbatim, in order:

1. Created `.venv` at repo root with `python -m venv .venv` (Python 3.14.7), upgraded pip (already at latest, 26.2.1 — no-op).
2. Merged the brief's `.gitignore` lines into the existing repo-root `.gitignore` (kept the existing `docs/mockups/*-directions.html` and `.playwright-mcp/` lines, appended the brief's lines). Also added `*.egg-info/` (see "Deviations" below).
3. Wrote `server/pyproject.toml` verbatim from the brief.
4. Installed the server package in editable mode with dev extras: `pip install -e ".[dev]"` from `server/`. All packages installed cleanly with prebuilt wheels for Python 3.14 (no source builds needed, no missing-wheel failures).
5. Wrote `server/tests/__init__.py` (empty) and `server/tests/test_health.py` verbatim.
6. Ran the test to confirm it failed before implementation existed (RED).
7. Wrote `server/app/clock.py` verbatim.
8. Wrote `server/app/config.py` verbatim.
9. Wrote `server/app/errors.py` verbatim.
10. Wrote `server/app/api/__init__.py` (empty), `server/app/api/health.py`, `server/app/__init__.py`, `server/run.py` — all verbatim from the brief.
11. Ran the full test suite (GREEN — 2 passed).
12. Committed `.gitignore` and `server/` with the exact commit subject from the brief, appended the required Co-Authored-By trailer.

## Files changed (all new except `.gitignore`)

- `.gitignore` (modified — merged in brief's lines + `*.egg-info/`)
- `server/pyproject.toml`
- `server/app/__init__.py`
- `server/app/config.py`
- `server/app/clock.py`
- `server/app/errors.py`
- `server/app/api/__init__.py`
- `server/app/api/health.py`
- `server/run.py`
- `server/tests/__init__.py`
- `server/tests/test_health.py`

## TDD evidence

**RED** — command:
```
cd server && . ../.venv/Scripts/activate && python -m pytest tests/test_health.py -q
```
Output:
```
ERROR collecting tests/test_health.py
ImportError while importing test module '...\server\tests\test_health.py'.
tests\test_health.py:1: in <module>
    from app import create_app
E   ImportError: cannot import name 'create_app' from 'app' (unknown location)
1 error in 0.13s
```
Why expected: `app/__init__.py` did not exist yet at this point (only `pyproject.toml` was installed editable, and `tests/` existed). The test module cannot import `create_app`, so collection fails — confirming the test genuinely exercises code that doesn't exist yet.

Note: the brief's expected message was `ModuleNotFoundError: No module named 'app'`. The actual failure was `ImportError: cannot import name 'create_app' from 'app' (unknown location)` instead. This is because `pip install -e ".[dev]"` (step 4, run before the test existed, per the brief's own step order) registered `app` as an editable-install namespace-package finder (PEP 660 / pip 26 behavior) even though no `app/` directory existed yet, so Python resolves `app` as an empty namespace package rather than raising `ModuleNotFoundError`. The RED intent — the test fails because the implementation doesn't exist — is satisfied; only the exact exception class/text differs from the brief's expectation, due to pip/Python version behavior. Not something I could avoid within the brief's prescribed step order.

**GREEN** — command:
```
cd server && . ../.venv/Scripts/activate && python -m pytest -q
```
Output:
```
..                                                                       [100%]
2 passed in 0.61s
```
Re-ran again after commit for confirmation:
```
tests\test_health.py ..                                                  [100%]
2 passed in 0.17s
```
No warnings, no errors — pristine.

## Exact package versions installed

```
Flask       3.1.3
SQLAlchemy  2.0.52
alembic     1.19.2
pydantic    2.13.5
bcrypt      5.0.0
flask-sock  0.7.0
```
(all installed with prebuilt wheels for Python 3.14 win_amd64; no ImportError, no missing-wheel fallbacks to source build)

Verification command output (step 4 of brief):
```
3.1.3 2.0.52 1.19.2 2.13.5 5.0.0
```
(A `DeprecationWarning` was printed for `flask.__version__` access in this ad-hoc diagnostic command only — not part of app code or the test suite, and the `filterwarnings = ["error::DeprecationWarning:app.*"]` pytest config only escalates warnings originating from the `app` package, so this is harmless and unrelated to test cleanliness.)

## Self-review

- **Completeness**: All files in the brief's file list created, with exactly the content specified. `Config` dataclass has all 9 required fields. `clock.now/freeze/advance/reset` all present. `AppError` and all 7 required subclasses (`NotFound, Unauthorized, Forbidden, ValidationFailed, ConsentError, TransitionError, Conflict`) present, plus `RateLimited` (in the brief's own step 9 code, not in the "Interfaces" list but part of the verbatim file — kept as specified). `create_app(config: Config | None = None) -> Flask` matches signature exactly.
- **Quality**: Names and structure match brief exactly; no naming deviations.
- **Discipline**: No extra files, no extra endpoints, no extra config fields, no speculative abstractions. Only deviation from a literal byte-for-byte "add only what the brief lists" is the `*.egg-info/` gitignore line — see below.
- **Testing**: Full suite run twice (before and after commit) — 2 passed, zero warnings, zero stray output both times.

## Deviations / issues / concerns

1. **`.gitignore`: added `*.egg-info/`.** Running `pip install -e ".[dev]"` (as instructed in step 4) generates `server/concierge_server.egg-info/` (build metadata). This directory is not in the brief's `.gitignore` list, and the brief's own global constraints say "never commit `.venv` or `*.db`" but doesn't mention egg-info. Since this is a pip-generated build artifact (analogous to `__pycache__/`, already in the ignore list) and committing it would pollute the repo with regenerable metadata, I added `*.egg-info/` to `.gitignore` before staging, and verified via `git add -n` that only the brief's exact 10 file paths (plus `.gitignore`) were staged for commit — the egg-info directory was correctly excluded. This is the one line I added beyond the brief's exact `.gitignore` content; everything else matches verbatim.
2. **RED-step exception text differs from the brief's exact wording** (see TDD evidence above) — behavioral difference due to pip 26 / Python 3.14 editable-install mechanics, not a code issue. The test still failed as expected before implementation existed.
3. **Ruff (not required by the brief's steps, run only as an extra sanity check)** flags two `UP017` suggestions in `app/clock.py` (`datetime.now(timezone.utc)` → `datetime.now(UTC)`). This file's content was specified verbatim by the brief, so I did not modify it — flagging for awareness only, not acted on, since it's brief-mandated content and ruff wasn't part of the required verification steps.
4. Confirmed via `git add -n` before committing that the staged file set exactly matches the brief's file list (11 files: `.gitignore` + the 10 `server/...` files) — no `server/data/`, no `.venv`, no `*.db` files were staged.

## Commit

```
859b27a feat(server): scaffold Flask app factory, config, clock, error shape

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
11 files changed, 249 insertions(+). Working tree clean after commit.

---

## Fix round 1 (review finding)

**Finding (Important):** `AppError.__init__` computed `self.message` from `self.code` *before* applying the `code=` override, so `AppError(code="CUSTOM_THING")` with no message produced a mismatched body: `code="CUSTOM_THING"` but `message="Bad request"` (derived from the un-overridden default code).

**What changed** — `server/app/errors.py`, `AppError.__init__`:

Before:
```python
def __init__(self, message: str | None = None, *, details: Any = None, code: str | None = None):
    super().__init__(message or self.code)
    self.message = message or self.code.replace("_", " ").capitalize()
    self.details = details
    if code:
        self.code = code
```

After:
```python
def __init__(self, message: str | None = None, *, details: Any = None, code: str | None = None):
    if code:
        self.code = code
    self.message = message or self.code.replace("_", " ").capitalize()
    self.details = details
    super().__init__(self.message)
```

The `code` override is applied first, then the default message is derived from the (possibly overridden) `self.code`, and `super().__init__` receives the final resolved message.

**New test** — `server/tests/test_errors.py` (new file, focused on this bug):
```python
from app.errors import AppError


def test_code_override_derives_matching_default_message():
    err = AppError(code="CUSTOM_THING")
    body = err.to_body()
    assert body["error"]["code"] == "CUSTOM_THING"
    assert body["error"]["message"] == "Custom thing"
```

**RED** (confirmed against old code via `git stash` of the `errors.py` fix only, new test kept in place):
```
python -m pytest tests/test_errors.py -q
```
```
FAILED tests/test_errors.py::test_code_override_derives_matching_default_message
AssertionError: assert 'Bad request' == 'Custom thing'
1 failed in 0.26s
```
This confirms the test reproduces the exact bug described in the finding (code overridden, message not re-derived from it).

**GREEN** — covering tests, then full suite, with the fix restored:
```
python -m pytest tests/test_health.py tests/test_errors.py -q
```
```
...                                                                      [100%]
3 passed in 0.18s
```
```
python -m pytest -q
```
```
...                                                                      [100%]
3 passed in 0.21s
```
No warnings, no stray output.

**Commit:**
```
b40401c fix(server): apply AppError code override before deriving the default message

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
2 files changed (`server/app/errors.py` modified, `server/tests/test_errors.py` added), 11 insertions, 3 deletions.
