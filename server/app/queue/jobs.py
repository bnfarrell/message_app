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
