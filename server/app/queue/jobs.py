from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import clock
from app.models import Job
from app.schemas.enums import JobStatus

RECURRING: dict[str, int] = {"sla.sweep": 30, "snooze.wake": 60, "pm.tick": 300,
                             "housekeeping.tick": 300}
STALE_SECONDS = 60


def enqueue(db: Session, type: str, payload: dict | None = None, run_at: datetime | None = None,
            max_attempts: int = 5) -> Job:
    job = Job(type=type, payload=payload or {}, run_at=run_at or clock.now(),
              max_attempts=max_attempts, status=JobStatus.queued)
    db.add(job)
    db.flush()
    return job


def claim_due(db: Session, limit: int = 20) -> list[Job]:
    """Claim due jobs with a compare-and-swap, not a row lock.

    SQLite compiles `.with_for_update(skip_locked=True)` away to a bare SELECT — no clause,
    no warning — so the lock this used to rely on never existed and two workers claimed the
    same row. The `status = 'queued'` predicate on the UPDATE is what `skip_locked` was meant
    to buy: a row another worker already took simply does not match, and is not claimed.
    Correct on PostgreSQL too.
    """
    now = clock.now()
    ids = db.scalars(select(Job.id)
                     .where(Job.status == JobStatus.queued, Job.run_at <= now)
                     .order_by(Job.run_at).limit(limit)).all()
    claimed = [jid for jid in ids
               if db.execute(update(Job)
                             .where(Job.id == jid, Job.status == JobStatus.queued)
                             .values(status=JobStatus.running, locked_at=now)).rowcount]
    db.flush()
    return list(db.scalars(select(Job).where(Job.id.in_(claimed))).all()) if claimed else []


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
    rows = db.scalars(select(Job).where(Job.status == JobStatus.running,
                                         Job.locked_at < cutoff)).all()
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
    if not interval:
        return
    # The same existence guard `ensure_recurring` has. Without it, two workers that both
    # completed one sweep each enqueue a successor and the chain doubles every interval.
    if db.scalar(select(Job.id).where(Job.type == job.type,
                                      Job.status.in_([JobStatus.queued, JobStatus.running]))):
        return
    enqueue(db, job.type, job.payload, run_at=clock.now() + timedelta(seconds=interval),
            max_attempts=1)
