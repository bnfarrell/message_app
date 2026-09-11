from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import notifications
from app.models import Conversation, Guest, Stay
from app.queue.handlers import handler
from app.realtime.broadcast import queue_event
from app.schemas.enums import ConversationStatus


def sweep_once(db: Session) -> int:
    now = clock.now()
    due = db.scalars(select(Conversation).where(
        Conversation.status == ConversationStatus.open,
        Conversation.sla_due_at.isnot(None), Conversation.sla_due_at < now,
        Conversation.sla_breach_notified_at.is_(None))).all()
    for c in due:
        guest = db.get(Guest, c.guest_id)
        stay = db.get(Stay, c.stay_id) if c.stay_id else None
        name = f"{guest.first_name or ''} {guest.last_name or ''}".strip() or guest.phone_e164
        room = f" · {stay.room_number}" if stay and stay.room_number else ""
        minutes = int((now - c.sla_due_at).total_seconds() // 60)
        notifications.notify_user_or_department(
            db, c.property_id, user_id=c.assigned_user_id, department_id=c.assigned_department_id,
            type="sla.breach", title=f"Response overdue: {name}{room}",
            body=f"No reply for {minutes} min past the SLA", entity_type="conversation", entity_id=c.id)
        c.sla_breach_notified_at = now
        queue_event(db, c.property_id, "conversation.updated", {"id": c.id})
    db.flush()
    return len(due)


@handler("sla.sweep")
def sla_sweep(db: Session, payload: dict) -> None:
    sweep_once(db)
