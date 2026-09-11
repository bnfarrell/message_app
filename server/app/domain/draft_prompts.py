from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit
from app.errors import NotFound
from app.models import Conversation, DraftPrompt, Guest, Stay, WorkOrder
from app.realtime.broadcast import queue_event
from app.schemas.enums import DraftPromptStatus


def draft_body(guest_first_name: str | None, room: str | None, title: str) -> str:
    name = guest_first_name or "there"
    where = f" in {room}" if room else ""
    return (f"Hi {name} — our team has taken care of \"{title}\"{where}. "
            f"Please text us if anything still isn't right.")


def create_for_completion(db: Session, wo: WorkOrder) -> DraftPrompt | None:
    """design.md §6.4: the highest-value twenty lines. Never sends; only proposes."""
    if not wo.source_conversation_id:
        return None
    conv = db.get(Conversation, wo.source_conversation_id)
    if conv is None:
        return None
    existing = db.scalar(select(DraftPrompt).where(DraftPrompt.work_order_id == wo.id,
                                                   DraftPrompt.status == DraftPromptStatus.pending))
    if existing:
        return existing
    guest = db.get(Guest, conv.guest_id)
    stay = db.get(Stay, conv.stay_id) if conv.stay_id else None
    room = stay.room_number if stay else wo.location_ref
    dp = DraftPrompt(property_id=wo.property_id, conversation_id=conv.id, work_order_id=wo.id,
                     body=draft_body(guest.first_name, room, wo.title),
                     status=DraftPromptStatus.pending)
    db.add(dp)
    db.flush()
    queue_event(db, wo.property_id, "draft_prompt.created",
                {"id": dp.id, "conversationId": conv.id, "workOrderId": wo.id, "body": dp.body})
    return dp


def dismiss(db: Session, property_id: str, conversation_id: str, prompt_id: str,
           actor_user_id: str) -> DraftPrompt:
    dp = db.scalar(select(DraftPrompt).where(DraftPrompt.id == prompt_id,
                                             DraftPrompt.property_id == property_id,
                                             DraftPrompt.conversation_id == conversation_id))
    if dp is None:
        raise NotFound("Prompt not found")
    if dp.status == DraftPromptStatus.pending:
        dp.status = DraftPromptStatus.dismissed
        dp.resolved_at = clock.now()
        dp.resolved_by_user_id = actor_user_id
        audit.record(db, property_id, actor_user_id, "draft_prompt.dismissed", "draft_prompt",
                     dp.id)
        queue_event(db, property_id, "conversation.updated", {"id": conversation_id})
    return dp
