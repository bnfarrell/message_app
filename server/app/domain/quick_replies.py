from __future__ import annotations

import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import conversations as conv_domain
from app.domain.sms import segment_count
from app.errors import Conflict, NotFound
from app.models import Guest, Property, QuickReply, Stay, UserAccount
from app.schemas.content import QuickReplyIn, QuickReplyOut, QuickReplyPatch, RenderedQuickReply

VARIABLES = ("guest_first_name", "room_number", "property_name", "agent_first_name",
            "departure_date")
FALLBACKS = {
    "guest_first_name": "there",
    "room_number": "your room",
    "property_name": "the hotel",
    "agent_first_name": "the front desk",
    "departure_date": "soon",
}
_HOLE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def interpolate(body: str, ctx: dict[str, str | None]) -> str:
    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in VARIABLES:
            return m.group(0)
        value = ctx.get(key)
        return str(value) if value not in (None, "") else FALLBACKS[key]

    return _HOLE.sub(_sub, body)


def list(db: Session, property_id: str, q: str | None = None, department_id: str | None = None,
         include_inactive: bool = False) -> list[QuickReplyOut]:
    stmt = select(QuickReply).where(QuickReply.property_id == property_id)
    if not include_inactive:
        stmt = stmt.where(QuickReply.active.is_(True))
    if department_id:
        stmt = stmt.where(or_(QuickReply.department_id == department_id,
                              QuickReply.department_id.is_(None)))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(QuickReply.shortcut).like(like),
                              func.lower(QuickReply.title).like(like),
                              func.lower(QuickReply.body).like(like)))
    rows = db.scalars(stmt.order_by(QuickReply.usage_count.desc(), QuickReply.shortcut)).all()
    return [QuickReplyOut.model_validate(r) for r in rows]


def get(db: Session, property_id: str, quick_reply_id: str) -> QuickReply:
    r = db.scalar(select(QuickReply).where(QuickReply.id == quick_reply_id,
                                            QuickReply.property_id == property_id))
    if r is None:
        raise NotFound("Quick reply not found")
    return r


def _assert_shortcut_free(db: Session, property_id: str, shortcut: str,
                          exclude_id: str | None = None) -> None:
    stmt = select(QuickReply.id).where(QuickReply.property_id == property_id,
                                        QuickReply.shortcut == shortcut)
    if exclude_id:
        stmt = stmt.where(QuickReply.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"Shortcut {shortcut} is already in use")


def create(db: Session, property_id: str, data: QuickReplyIn) -> QuickReply:
    # The pre-check below narrows the common case to a clean 409, but two requests can still race
    # between the check and the insert; the DB's unique constraint is the real guard, so catch its
    # violation too rather than let a collision surface as an unhandled IntegrityError (see Task 16
    # review round 1, matching the app.domain.guests.find_or_create_by_phone remedy).
    _assert_shortcut_free(db, property_id, data.shortcut)
    r = QuickReply(property_id=property_id, **data.model_dump())
    try:
        with db.begin_nested():
            db.add(r)
            db.flush()
    except IntegrityError:
        raise Conflict(f"Shortcut {data.shortcut} is already in use") from None
    return r


def update(db: Session, property_id: str, quick_reply_id: str, data: QuickReplyPatch) -> QuickReply:
    r = get(db, property_id, quick_reply_id)
    changes = data.model_dump(exclude_unset=True)
    if "shortcut" in changes and changes["shortcut"]:
        _assert_shortcut_free(db, property_id, changes["shortcut"], exclude_id=r.id)
    for k, v in changes.items():
        setattr(r, k, v)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise Conflict(f"Shortcut {changes.get('shortcut')} is already in use") from None
    return r


def delete(db: Session, property_id: str, quick_reply_id: str) -> None:
    db.delete(get(db, property_id, quick_reply_id))


def context_for_conversation(db: Session, property_id: str, conversation_id: str,
                             agent_user_id: str | None) -> dict:
    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    stay = db.get(Stay, conv.stay_id) if conv.stay_id else None
    prop = db.get(Property, property_id)
    agent = db.get(UserAccount, agent_user_id) if agent_user_id else None
    return {
        "guest_first_name": guest.first_name,
        "room_number": stay.room_number if stay else None,
        "property_name": prop.name,
        "agent_first_name": agent.first_name if agent else None,
        "departure_date": stay.departure_date.strftime("%A, %b %d") if stay else None,
    }


def preview(db: Session, property_id: str, body: str, conversation_id: str | None,
            agent_user_id: str | None) -> RenderedQuickReply:
    """Renders arbitrary body text without touching a single row.

    Deliberately not `render()`: that one bumps `usage_count` (which the admin table displays as
    "Uses"), needs a saved row and a real conversation, and is gated on `reply` — a capability
    `corporate` does not hold even though it can open the admin screen. Every variable with no
    context — including the no-conversation case — falls back through `interpolate`.
    """
    ctx = (context_for_conversation(db, property_id, conversation_id, agent_user_id)
           if conversation_id else {})
    rendered = interpolate(body, ctx)
    return RenderedQuickReply(body=rendered, segments=segment_count(rendered),
                              characters=len(rendered))


def render(db: Session, property_id: str, quick_reply_id: str, conversation_id: str,
           agent_user_id: str | None) -> RenderedQuickReply:
    r = get(db, property_id, quick_reply_id)
    body = interpolate(r.body,
                       context_for_conversation(db, property_id, conversation_id, agent_user_id))
    r.usage_count += 1
    return RenderedQuickReply(body=body, segments=segment_count(body), characters=len(body))
