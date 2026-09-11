import shutil

import pytest
from sqlalchemy import Select, event, select, update

from app import clock, create_app
from app.config import Config
from app.models import Job
from app.queue import jobs
from app.queue.handlers import HANDLERS, handler
from app.queue.worker import Worker
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


def test_start_worker_guard_avoids_duplicate_start_under_reloader(
    template_db_path, tmp_path, monkeypatch
):
    """Regression: create_app must start the worker exactly once per real process.

    Under the Werkzeug reloader (USE_RELOADER=1, set by the dev entrypoints that pass
    debug=True), create_app() runs once in the parent monitor process (no WERKZEUG_RUN_MAIN)
    and once in the child (WERKZEUG_RUN_MAIN "true"). Only the child should start the worker.
    With no reloader there is a single process and it must start it.

    The guard deliberately does NOT ask is_production: that made forgetting FLASK_ENV on a
    gunicorn deployment mean "nothing is ever delivered", silently, and put job delivery on the
    same switch as dev-endpoint data exposure.
    """
    started = []
    monkeypatch.setattr(Worker, "start", lambda self: started.append(True))

    def build_app(use_reloader: bool, werkzeug_run_main: str | None, env: str = "development"
                  ) -> list:
        started.clear()
        if werkzeug_run_main is None:
            monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
        else:
            monkeypatch.setenv("WERKZEUG_RUN_MAIN", werkzeug_run_main)
        db_path = tmp_path / f"guard-{env}-{use_reloader}-{werkzeug_run_main}.db"
        shutil.copy(template_db_path, db_path)
        clock.freeze(clock.now())
        cfg = Config(
            DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
            TESTING=True,
            START_WORKER=True,
            ENV=env,
            SESSION_SECRET="a-real-secret",
            USE_RELOADER=use_reloader,
            PMS_TICK_SECONDS=0,
        )
        application = create_app(cfg)
        application.extensions["db"].engine.dispose()
        return started[:]

    try:
        # 1. production, no reloader at all -> the single run starts it.
        assert build_app(False, None, env="production") == [True]
        # 2. dev, parent monitor process (no WERKZEUG_RUN_MAIN yet) -> must NOT start.
        assert build_app(True, None) == []
        # 3. dev, reloader child (WERKZEUG_RUN_MAIN=true) -> starts it.
        assert build_app(True, "true") == [True]
        # 4. a deployment that forgot FLASK_ENV but runs under gunicorn (no reloader) still
        #    starts it: job delivery must not depend on the production flag.
        assert build_app(False, None) == [True]
    finally:
        clock.reset()


def test_claim_due_does_not_take_a_row_another_worker_claimed_mid_select(app, database):
    """Two workers must never both claim one job.

    SQLite silently drops `.with_for_update(skip_locked=True)` — it compiles to a bare
    `SELECT job.id FROM job`, with no warning — so the claim has to be a compare-and-swap:
    the UPDATE's own `status = 'queued'` predicate is what makes a contended row simply not
    claimed. The listener below fires between claim_due's SELECT and its UPDATE, which is
    exactly the window the real race lives in, so the contention is deterministic rather
    than timing-dependent.
    """
    with database.session() as db:
        job = jobs.enqueue(db, "test.ok", {})

    stolen: list[str] = []

    def steal(conn, clauseelement, multiparams, params, execution_options, result):
        if stolen or not isinstance(clauseelement, Select):
            return
        stolen.append(job.id)
        with database.session() as other:
            other.execute(
                update(Job).where(Job.id == job.id)
                .values(status=JobStatus.running, locked_at=clock.now())
            )

    event.listen(database.engine, "after_execute", steal)
    try:
        with database.session() as db:
            assert jobs.claim_due(db) == []
    finally:
        event.remove(database.engine, "after_execute", steal)

    assert stolen == [job.id], "the contending claim never ran; the test proves nothing"


def test_schedule_next_recurrence_leaves_exactly_one_successor(app, database):
    """Called twice for the same type it must enqueue once.

    worker.tick() calls this on every completed recurring job. Without the existence guard
    two workers that both completed the same sweep each enqueue a successor, and the chain
    doubles every interval — 1, 2, 4, 8 — which is how a 30-second sweep reached 2.7M rows.
    """
    jobs.RECURRING["test.ok"] = 30
    try:
        with database.session() as db:
            job = jobs.enqueue(db, "test.ok", {})
            jobs.complete(db, job)
            jobs.schedule_next_recurrence(db, job)
            jobs.schedule_next_recurrence(db, job)
            pending = db.scalars(select(Job).where(Job.type == "test.ok",
                                                   Job.status == JobStatus.queued)).all()
            assert len(pending) == 1
            assert (pending[0].run_at - clock.now()).total_seconds() == pytest.approx(30, abs=1)
    finally:
        jobs.RECURRING.pop("test.ok", None)
