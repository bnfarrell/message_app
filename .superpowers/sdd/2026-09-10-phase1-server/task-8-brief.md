### Task 8: Job queue and worker

**Files:**
- Create: `server/app/queue/__init__.py`, `server/app/queue/jobs.py`, `server/app/queue/worker.py`, `server/app/queue/handlers/__init__.py`, `server/tests/test_queue.py`
- Modify: `server/app/__init__.py` (start worker when `START_WORKER`), `server/tests/conftest.py` (add `worker` fixture)

**Interfaces:**
- Produces: `jobs.enqueue(db, type, payload, run_at=None, max_attempts=5) -> Job`; `jobs.claim_due(db, limit=20) -> list[Job]`; `jobs.complete(db, job)`; `jobs.fail(db, job, exc)`; `jobs.reclaim_stale(db, older_than_seconds=60) -> int`; `jobs.ensure_recurring(db, type, payload=None) -> Job | None`; `jobs.RECURRING: dict[str, int]` (type → interval seconds: `sla.sweep: 30`, `snooze.wake: 60`, `pms.tick: <config>`); `handlers.HANDLERS`, `@handlers.handler("type")`, `handlers.load_all()`; `Worker(app, interval=0.5)` with `tick() -> int`, `start()`, `stop()`; test fixture `worker` (a `Worker` bound to the test app; call `worker.tick()`).

- [ ] **Step 1: Write the failing tests**

`server/tests/test_queue.py`:
```python
import pytest
from sqlalchemy import select

from app import clock
from app.models import Job
from app.queue import jobs
from app.queue.handlers import HANDLERS, handler
from app.schemas.enums import JobStatus


@pytest.fixture()
def fake_handlers():
    calls = []

    @handler("test.ok")
    def _ok(db, payload):
        calls.append(("ok", payload))

    @handler("test.boom")
    def _boom(db, payload):
        calls.append(("boom", payload))
        raise RuntimeError("kaboom")

    yield calls
    HANDLERS.pop("test.ok", None)
    HANDLERS.pop("test.boom", None)


def test_enqueue_and_tick_runs_handler(app, database, worker, fake_handlers):
    with database.session() as db:
        job = jobs.enqueue(db, "test.ok", {"n": 1})
    assert worker.tick() == 1
    assert fake_handlers == [("ok", {"n": 1})]
    with database.session() as db:
        assert db.get(Job, job.id).status == JobStatus.done


def test_future_jobs_wait_for_their_time(app, database, worker, fake_handlers):
    from datetime import timedelta

    with database.session() as db:
        jobs.enqueue(db, "test.ok", {}, run_at=clock.now() + timedelta(seconds=30))
    assert worker.tick() == 0
    clock.advance(seconds=31)
    assert worker.tick() == 1


def test_failure_retries_with_backoff_then_dies(app, database, worker, fake_handlers):
    with database.session() as db:
        job = jobs.enqueue(db, "test.boom", {}, max_attempts=3)
    for attempt in range(1, 4):
        assert worker.tick() == 1
        with database.session() as db:
            j = db.get(Job, job.id)
            assert j.attempts == attempt
            assert "kaboom" in (j.last_error or "")
            if attempt < 3:
                assert j.status == JobStatus.queued
                assert (j.run_at - clock.now()).total_seconds() == pytest.approx(2**attempt, abs=1)
                clock.advance(seconds=2**attempt + 1)
            else:
                assert j.status == JobStatus.dead
    assert worker.tick() == 0
    assert len(fake_handlers) == 3


def test_unknown_job_type_is_marked_dead(app, database, worker):
    with database.session() as db:
        job = jobs.enqueue(db, "nope.nothing", {})
    worker.tick()
    with database.session() as db:
        j = db.get(Job, job.id)
        assert j.status == JobStatus.dead and "No handler" in j.last_error


def test_recurring_job_reenqueues_itself(app, database, worker, fake_handlers):
    jobs.RECURRING["test.ok"] = 30
    try:
        with database.session() as db:
            first = jobs.ensure_recurring(db, "test.ok")
            assert jobs.ensure_recurring(db, "test.ok") is None  # already queued
        worker.tick()
        with database.session() as db:
            queued = db.scalars(select(Job).where(Job.type == "test.ok",
                                                  Job.status == JobStatus.queued)).all()
            assert len(queued) == 1 and queued[0].id != first.id
            assert (queued[0].run_at - clock.now()).total_seconds() == pytest.approx(30, abs=1)
    finally:
        jobs.RECURRING.pop("test.ok", None)


def test_stale_running_jobs_are_reclaimed(app, database, worker, fake_handlers):
    with database.session() as db:
        job = jobs.enqueue(db, "test.ok", {})
        job.status = JobStatus.running
        job.locked_at = clock.now()
    clock.advance(seconds=61)
    with database.session() as db:
        assert jobs.reclaim_stale(db) == 1
    assert worker.tick() == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_queue.py -q`
Expected: FAIL with `ModuleNotFoundError: app.queue`.

- [ ] **Step 3: Write the handler registry**

`server/app/queue/__init__.py` — empty.

`server/app/queue/handlers/__init__.py`:
```python
from __future__ import annotations

import importlib
from typing import Callable

from sqlalchemy.orm import Session

Handler = Callable[[Session, dict], None]
HANDLERS: dict[str, Handler] = {}

MODULES = ("outbound", "mock_delivery", "sla", "snooze", "pms")


def handler(job_type: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[job_type] = fn
        return fn

    return deco


def load_all() -> None:
    """Import every handler module so its @handler decorators run. Safe to call repeatedly."""
    for name in MODULES:
        try:
            importlib.import_module(f"app.queue.handlers.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"app.queue.handlers.{name}":
                raise
```

(Modules that don't exist yet are skipped; Tasks 9, 13 and 20 add them.)

- [ ] **Step 4: Write `app/queue/jobs.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Job
from app.schemas.enums import JobStatus

RECURRING: dict[str, int] = {"sla.sweep": 30, "snooze.wake": 60}
STALE_SECONDS = 60


def enqueue(db: Session, type: str, payload: dict | None = None, run_at: datetime | None = None,
            max_attempts: int = 5) -> Job:
    job = Job(type=type, payload=payload or {}, run_at=run_at or clock.now(),
              max_attempts=max_attempts, status=JobStatus.queued)
    db.add(job)
    db.flush()
    return job


def claim_due(db: Session, limit: int = 20) -> list[Job]:
    now = clock.now()
    due = db.scalars(
        select(Job).where(Job.status == JobStatus.queued, Job.run_at <= now)
        .order_by(Job.run_at).limit(limit).with_for_update(skip_locked=True)
    ).all()
    for job in due:
        job.status = JobStatus.running
        job.locked_at = now
    db.flush()
    return due


def complete(db: Session, job: Job) -> None:
    job.status = JobStatus.done
    job.finished_at = clock.now()
    job.locked_at = None


def fail(db: Session, job: Job, exc: BaseException, *, retry: bool = True) -> None:
    job.attempts += 1
    job.last_error = repr(exc)[:2000]
    job.locked_at = None
    if retry and job.attempts < job.max_attempts:
        job.status = JobStatus.queued
        job.run_at = clock.now() + timedelta(seconds=2**job.attempts)
    else:
        job.status = JobStatus.dead
        job.finished_at = clock.now()


def reclaim_stale(db: Session, older_than_seconds: int = STALE_SECONDS) -> int:
    cutoff = clock.now() - timedelta(seconds=older_than_seconds)
    rows = db.scalars(select(Job).where(Job.status == JobStatus.running, Job.locked_at < cutoff)).all()
    for job in rows:
        job.status = JobStatus.queued
        job.locked_at = None
    return len(rows)


def ensure_recurring(db: Session, type: str, payload: dict | None = None) -> Job | None:
    exists = db.scalar(select(Job.id).where(Job.type == type,
                                            Job.status.in_([JobStatus.queued, JobStatus.running])))
    if exists:
        return None
    return enqueue(db, type, payload or {}, max_attempts=1)


def schedule_next_recurrence(db: Session, job: Job) -> None:
    interval = RECURRING.get(job.type)
    if interval:
        enqueue(db, job.type, job.payload, run_at=clock.now() + timedelta(seconds=interval),
                max_attempts=1)
```

`with_for_update(skip_locked=True)` is a no-op on SQLite and correct on Postgres.

- [ ] **Step 5: Write `app/queue/worker.py`**

```python
from __future__ import annotations

import logging
import threading

from flask import Flask

from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all

log = logging.getLogger("worker")


class Worker:
    def __init__(self, app: Flask, interval: float = 0.5):
        self.app = app
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        load_all()

    def tick(self) -> int:
        """Run one pass. Returns how many jobs were executed (successfully or not)."""
        database = self.app.extensions["db"]
        with self.app.app_context():
            with database.session() as db:
                jobs.reclaim_stale(db)
                claimed = jobs.claim_due(db)
                claimed_ids = [(j.id, j.type, dict(j.payload)) for j in claimed]
            ran = 0
            for job_id, job_type, payload in claimed_ids:
                ran += 1
                fn = HANDLERS.get(job_type)
                try:
                    if fn is None:
                        raise LookupError(f"No handler for job type {job_type!r}")
                    with database.session() as db:
                        fn(db, payload)
                        job = db.get(jobs.Job, job_id)
                        jobs.complete(db, job)
                        jobs.schedule_next_recurrence(db, job)
                except Exception as exc:  # noqa: BLE001 — the worker must survive any handler error
                    log.exception("job %s (%s) failed", job_id, job_type)
                    with database.session() as db:
                        job = db.get(jobs.Job, job_id)
                        jobs.fail(db, job, exc, retry=not isinstance(exc, LookupError))
                        if job.type in jobs.RECURRING and job.status != jobs.JobStatus.queued:
                            jobs.schedule_next_recurrence(db, job)
            return ran

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("worker tick crashed")
            self._stop.wait(self.interval)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
```

`jobs.py` must also export `Job` and `JobStatus` for the worker's `db.get(jobs.Job, ...)` — they are already imported there, so `jobs.Job` and `jobs.JobStatus` resolve.

- [ ] **Step 6: Wire the worker into the app factory and tests**

In `create_app`, after blueprints:
```python
    import os

    from app.queue import jobs as _jobs
    from app.queue.worker import Worker

    _jobs.RECURRING["pms.tick"] = config.PMS_TICK_SECONDS or 0
    if not config.PMS_TICK_SECONDS:
        _jobs.RECURRING.pop("pms.tick", None)
    app.extensions["worker"] = Worker(app)
    under_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if config.START_WORKER and (under_reloader or not app.debug):
        with app.extensions["db"].session() as db:
            for job_type in _jobs.RECURRING:
                _jobs.ensure_recurring(db, job_type)
        app.extensions["worker"].start()
```

`run.py` runs with `debug=True` in development, so the Werkzeug reloader is on and only the child process (`WERKZEUG_RUN_MAIN=true`) starts the worker.

In `server/tests/conftest.py` add:
```python
@pytest.fixture()
def worker(app):
    return app.extensions["worker"]
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): SQLite-backed job queue with retry/backoff/dead-letter and in-process worker"
```

---

