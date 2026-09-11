from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Conversation
from app.queue.handlers import handler
from app.realtime.broadcast import queue_event
from app.schemas.enums import ConversationStatus


def wake_once(db: Session) -> int:
    now = clock.now()
    due = db.scalars(select(Conversation).where(
        Conversation.status == ConversationStatus.snoozed,
        Conversation.snoozed_until.isnot(None), Conversation.snoozed_until <= now)).all()
    for c in due:
        c.status = ConversationStatus.open
        c.snoozed_until = None
        queue_event(db, c.property_id, "conversation.updated", {"id": c.id})
    db.flush()
    return len(due)


@handler("snooze.wake")
def snooze_wake(db: Session, payload: dict) -> None:
    wake_once(db)
