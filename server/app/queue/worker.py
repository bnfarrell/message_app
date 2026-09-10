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
