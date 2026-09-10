from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, notifications
from app.domain import conversations as conv_domain
from app.models import InternalNote, PropertyMembership, UserAccount
from app.schemas.conversations import NoteOut

_MENTION = re.compile(r"@([A-Za-z][\w'-]*)")


def _resolve_mentions(db: Session, property_id: str, body: str) -> list[str]:
    names = {m.lower() for m in _MENTION.findall(body)}
    if not names:
        return []
    rows = db.execute(
        select(UserAccount.id, UserAccount.first_name)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .where(PropertyMembership.property_id == property_id)
    ).all()
    return [uid for uid, first in rows if first.lower() in names]


def create(db: Session, property_id: str, conversation_id: str, author_user_id: str, body: str) -> InternalNote:
    conv = conv_domain.get(db, property_id, conversation_id)
    mentions = _resolve_mentions(db, property_id, body)
    note = InternalNote(conversation_id=conv.id, property_id=property_id, author_user_id=author_user_id,
                        body=body.strip(), mentions=mentions)
    db.add(note)
    db.flush()
    author = db.get(UserAccount, author_user_id)
    for uid in mentions:
        if uid != author_user_id:
            notifications.create(db, property_id, uid, "note.mention",
                                 f"{author.first_name} mentioned you", body=body[:140],
                                 entity_type="conversation", entity_id=conv.id)
    audit.record(db, property_id, author_user_id, "note.created", "internal_note", note.id,
                 after={"conversation_id": conv.id})
    conv_domain.touch_updated(db, conv)
    return note


def list_for(db: Session, property_id: str, conversation_id: str) -> list[NoteOut]:
    rows = db.execute(
        select(InternalNote, UserAccount)
        .join(UserAccount, UserAccount.id == InternalNote.author_user_id)
        .where(InternalNote.conversation_id == conversation_id, InternalNote.property_id == property_id)
        .order_by(InternalNote.created_at)
    ).all()
    return [NoteOut(id=n.id, author_user_id=n.author_user_id, author_name=f"{u.first_name} {u.last_name}",
                    body=n.body, mentions=list(n.mentions or []), created_at=n.created_at)
            for n, u in rows]
