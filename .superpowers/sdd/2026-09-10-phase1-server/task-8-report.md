# Task 8 Report: Job queue and worker

## What was implemented

Followed the brief verbatim, no deviations:

- `server/app/queue/__init__.py` — empty package marker.
- `server/app/queue/handlers/__init__.py` — `HANDLERS` registry, `@handler("type")` decorator,
  `load_all()` that imports `outbound`, `mock_delivery`, `sla`, `snooze`, `pms` handler modules,
  swallowing `ModuleNotFoundError` only for exactly those (not-yet-existing) module names.
- `server/app/queue/jobs.py` — `enqueue`, `claim_due` (SELECT ... FOR UPDATE SKIP LOCKED, no-op on
  SQLite), `complete`, `fail` (exponential backoff `2**attempts` seconds, dead-letters at
  `max_attempts`), `reclaim_stale`, `ensure_recurring`, `schedule_next_recurrence`, and the
  `RECURRING` dict (`sla.sweep: 30`, `snooze.wake: 60`; `pms.tick` added by the app factory).
- `server/app/queue/worker.py` — `Worker` class: `tick()` reclaims stale jobs, claims due jobs in one
  session, then runs each job's handler in its own fresh `database.session()` (so each job's
  realtime events flush independently on that job's own commit), marking unknown job types dead via
  a `LookupError` (non-retryable). `start()`/`stop()` run/stop a daemon background thread.
- `server/app/__init__.py` — after blueprint registration: registers `pms.tick` into `RECURRING`
  from `config.PMS_TICK_SECONDS` (removed if falsy, as in the test config which sets it to 0),
  constructs `app.extensions["worker"] = Worker(app)`, and — only when `START_WORKER` is set and
  either under the Werkzeug reloader child process or not in debug mode — seeds the recurring jobs
  and starts the worker thread.
- `server/tests/conftest.py` — added `worker` fixture returning `app.extensions["worker"]`.
- `server/tests/test_queue.py` — the six brief-verbatim tests.

No migration changes needed; `Job`/`JobStatus` already existed per the brief's context notes.

## What was tested and results

Focused suite:
```
../.venv/Scripts/python.exe -m pytest tests/test_queue.py -q
......                                                                   [100%]
6 passed in 0.72s
```
Also ran with `-W error::DeprecationWarning` to confirm `with_for_update(skip_locked=True)` raises
no SQLAlchemy warning on SQLite — none appeared.

Full suite:
```
../.venv/Scripts/python.exe -m pytest -q
................................................................         [100%]
64 passed in 3.06s
```
64 = 58 pre-existing + 6 new. Output pristine, no warnings.

## TDD Evidence

**RED** — before any `app/queue` code existed, ran:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_queue.py -q
```
Output:
```
ERROR collecting tests/test_queue.py
...
E   ModuleNotFoundError: No module named 'app.queue'
1 error in 0.18s
```
This is exactly the failure the brief's Step 2 predicts (`ModuleNotFoundError: app.queue`) — the
test file imports `from app.queue import jobs` before that package exists, so collection fails
with the module-not-found error, not an assertion failure. Expected and correct for this stage.

**GREEN** — after implementing Steps 3-6 (queue package, jobs, worker, app wiring, conftest
fixture), re-ran the same command:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_queue.py -q
......                                                                   [100%]
6 passed in 0.72s
```
All 6 tests pass. Then ran the full suite (Step 7): 64 passed, pristine.

## Files changed

- `server/app/queue/__init__.py` (new)
- `server/app/queue/handlers/__init__.py` (new)
- `server/app/queue/jobs.py` (new)
- `server/app/queue/worker.py` (new)
- `server/app/__init__.py` (modified — worker wiring appended after blueprint registration)
- `server/tests/conftest.py` (modified — added `worker` fixture)
- `server/tests/test_queue.py` (new)

## Self-review findings

- Diffs to `app/__init__.py` and `tests/conftest.py` are exactly the brief's Step 6 snippets,
  appended/inserted without touching surrounding code.
- New files are brief-verbatim; left the `jobs.Job`/`jobs.JobStatus` attribute-lookup style in
  `worker.py` as instructed rather than adding a separate import.
- Did not run `ruff` reformatting on brief-verbatim code, per project convention (single pass at
  Task 24).
- Verified staged git diff before committing contained only `server/` source files — no `.db`
  files or `.venv` were staged.
- No orphaned imports/dead code introduced.

## Issues or concerns

None. No brief defects found — all six tests passed as specified, backoff timing
(`2**attempts` seconds) and dead-lettering behavior matched exactly, and `with_for_update
(skip_locked=True)` produced no warning on SQLite.

---

## Fix round 1: reloader-guard defect (Important, plan-mandated)

### Finding

Review found that `server/app/__init__.py`'s worker-start guard could never distinguish the
Werkzeug reloader's parent-monitor process from its child:

```python
under_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
if config.START_WORKER and (under_reloader or not app.debug):
```

`app.debug` is Flask's default `False` at the moment `create_app()` runs in every scenario,
because nothing in `create_app` sets `app.config["DEBUG"]` — `run.py` passes `debug=...` to
`app.run()` only after `create_app()` has already returned. So `not app.debug` was always `True`,
meaning with `START_WORKER=1` in dev both the reloader's parent-monitor process and its child
process would start a `Worker`, producing two threads polling and executing jobs against the same
SQLite database.

### Fix

Gated on `config.is_production` (decided from `Config.ENV`, before Flask ever touches `debug`)
instead of `app.debug`:

```python
under_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
if config.START_WORKER and (under_reloader or config.is_production):
```

This matches `run.py`'s own derivation of `debug=not cfg.is_production`: production (no reloader)
starts the worker on its single run; dev starts it only in the reloader's child process.

### Regression test added

`server/tests/test_queue.py::test_start_worker_guard_avoids_duplicate_start_under_reloader` builds
three `create_app()` instances with `START_WORKER=True`, monkeypatching `Worker.start` to record
calls instead of spawning a thread, and toggling `WERKZEUG_RUN_MAIN` via
`monkeypatch.setenv`/`delenv` (auto-restored by the fixture, so no env leakage to other tests):

1. `ENV="production"`, no `WERKZEUG_RUN_MAIN` → worker started.
2. `ENV="development"`, no `WERKZEUG_RUN_MAIN` (parent-monitor process) → worker NOT started.
3. `ENV="development"`, `WERKZEUG_RUN_MAIN="true"` (reloader child) → worker started.

Before writing up this report I confirmed the test actually catches the regression: I temporarily
restored the old `not app.debug` condition, ran
`../.venv/Scripts/python.exe -m pytest tests/test_queue.py -q -k guard`, and case 2 failed
(`assert [True] == []`, i.e. the worker started when it must not). I then restored the fixed
condition and reran — all cases passed. This confirms the test is a real regression guard, not a
tautology.

### Covering tests run

Focused:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_queue.py -q
.......                                                                  [100%]
7 passed in 0.91s
```

Full suite:
```
cd server && ../.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 4.79s
```
(91 = 58 from tasks 1-7 + 7 in test_queue.py + jobs from tasks 9/10's own test files that landed
on top of my Task 8 commit before this fix round.) Output pristine, no warnings.

### Files changed (this fix round)

- `server/app/__init__.py` — one-line condition fix.
- `server/tests/test_queue.py` — added the regression test and its imports.
