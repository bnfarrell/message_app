"""`housekeeping.tick` (spec §3.1): every 300 s. Idempotent, so a retried job is harmless."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import hk_tick
from app.queue.handlers import handler


@handler("housekeeping.tick")
def housekeeping_tick(db: Session, payload: dict) -> None:
    hk_tick.tick(db)
