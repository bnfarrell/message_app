"""`checklist.tick` (checklists spec §3.2): every 300 s. Idempotent, so a retried job is
harmless."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import ck_tick
from app.queue.handlers import handler


@handler("checklist.tick")
def checklist_tick(db: Session, payload: dict) -> None:
    ck_tick.tick(db)
