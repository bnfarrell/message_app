from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, notifications
from app.errors import NotFound, ValidationFailed
from app.models import (
    Department,
    PropertyMembership,
    StaffConversation,
    StaffConversationParticipant,
    StaffMessage,
    UserAccount,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import StaffConversationKind
from app.schemas.staff_messages import (
    AddParticipantsRequest,
    CreateStaffConversationRequest,
    GroupPatch,
    StaffConversationDetail,
    StaffConversationOut,
    StaffDirectoryEntryOut,
    StaffMessageOut,
    StaffParticipantOut,
)

MAX_MESSAGES = 200


def _assert_member(db: Session, property_id: str, user_id: str) -> None:
    if not db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.property_id == property_id, PropertyMembership.user_id == user_id)):
        raise ValidationFailed("User is not a member of this property")


def get_or_create_all_conversation(db: Session, property_id: str) -> StaffConversation:
    conv = db.scalar(select(StaffConversation).where(
        StaffConversation.property_id == property_id,
        StaffConversation.kind == StaffConversationKind.all))
    if conv is not None:
        return conv
    conv = StaffConversation(property_id=property_id, kind=StaffConversationKind.all, name="#ALL")
    db.add(conv)
    db.flush()
    return conv


def ensure_participant(db: Session, conversation_id: str,
                       user_id: str) -> StaffConversationParticipant:
    row = db.scalar(select(StaffConversationParticipant).where(
        StaffConversationParticipant.conversation_id == conversation_id,
        StaffConversationParticipant.user_id == user_id))
    if row is not None:
        return row
    row = StaffConversationParticipant(conversation_id=conversation_id, user_id=user_id)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # Concurrent double-join (e.g. two tabs both opening #ALL for the first time).
        row = db.scalar(select(StaffConversationParticipant).where(
            StaffConversationParticipant.conversation_id == conversation_id,
            StaffConversationParticipant.user_id == user_id))
    return row


def find_dm(db: Session, property_id: str, user_a: str, user_b: str) -> StaffConversation | None:
    P = StaffConversationParticipant
    matching = (
        select(P.conversation_id)
        .join(StaffConversation, StaffConversation.id == P.conversation_id)
        .where(StaffConversation.property_id == property_id,
               StaffConversation.kind == StaffConversationKind.dm,
               P.user_id.in_([user_a, user_b]))
        .group_by(P.conversation_id)
        .having(func.count(func.distinct(P.user_id)) == 2)
    )
    # A dm conversation has exactly 2 participants by construction (never gains more — only
    # groups are editable), so both ids present among its (exactly 2) participants means the
    # pair is exactly {user_a, user_b}.
    return db.scalar(select(StaffConversation).where(StaffConversation.id.in_(matching)))


def create_conversation(db: Session, property_id: str, actor_user_id: str,
                        data: CreateStaffConversationRequest) -> tuple[StaffConversation, bool]:
    """Returns (conversation, created) — `created=False` when a dm request deduped to an
    existing thread, so the API layer can answer 200 instead of 201."""
    if data.kind == StaffConversationKind.dm:
        if not data.user_id:
            raise ValidationFailed("userId is required for a dm")
        if data.user_id == actor_user_id:
            raise ValidationFailed("Cannot start a dm with yourself")
        _assert_member(db, property_id, data.user_id)
        existing = find_dm(db, property_id, actor_user_id, data.user_id)
        if existing is not None:
            return existing, False
        conv = StaffConversation(property_id=property_id, kind=StaffConversationKind.dm,
                                 created_by_user_id=actor_user_id)
        db.add(conv)
        db.flush()
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=actor_user_id))
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=data.user_id))
        db.flush()
        queue_event(db, property_id, "staff_conversation.created", {"id": conv.id})
        return conv, True

    if not data.name or not data.user_ids:
        raise ValidationFailed("name and userIds are required for a group")
    for uid in data.user_ids:
        _assert_member(db, property_id, uid)
    conv = StaffConversation(property_id=property_id, kind=StaffConversationKind.group,
                             name=data.name.strip(), created_by_user_id=actor_user_id)
    db.add(conv)
    db.flush()
    member_ids = dict.fromkeys([actor_user_id, *data.user_ids])  # de-dupe, keep order
    for uid in member_ids:
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=uid))
    db.flush()
    queue_event(db, property_id, "staff_conversation.created", {"id": conv.id})
    return conv, True


def get(db: Session, property_id: str, conversation_id: str) -> StaffConversation:
    conv = db.scalar(select(StaffConversation).where(
        StaffConversation.id == conversation_id, StaffConversation.property_id == property_id))
    if conv is None:
        raise NotFound("Conversation not found")
    return conv


def get_for_participant(db: Session, property_id: str, conversation_id: str,
                        user_id: str) -> StaffConversation:
    conv = get(db, property_id, conversation_id)
    is_participant = db.scalar(select(StaffConversationParticipant.id).where(
        StaffConversationParticipant.conversation_id == conv.id,
        StaffConversationParticipant.user_id == user_id))
    # #ALL is implicitly open to every property member: joining lazily here, rather than
    # 404ing until some earlier list-view happened to trigger the join, means a direct link to
    # the all-channel works for a user who has never opened Messages before.
    if is_participant is None and conv.kind == StaffConversationKind.all:
        ensure_participant(db, conv.id, user_id)
    elif is_participant is None:
        raise NotFound("Conversation not found")
    return conv


def _display(conv: StaffConversation, participants: list[StaffParticipantOut],
            viewer_user_id: str) -> tuple[str, str | None, str | None]:
    """(display_name, avatar_url, other_user_id) for a viewer."""
    if conv.kind == StaffConversationKind.dm:
        other = next((p for p in participants if p.user_id != viewer_user_id), None)
        name = f"{other.first_name} {other.last_name}" if other else "Unknown"
        return name, other.avatar_url if other else None, other.user_id if other else None
    return conv.name or "Group", conv.avatar_url, None


def _participants_out(db: Session, conv: StaffConversation) -> list[StaffParticipantOut]:
    rows = db.execute(
        select(UserAccount, PropertyMembership)
        .join(StaffConversationParticipant, StaffConversationParticipant.user_id == UserAccount.id)
        .join(PropertyMembership, (PropertyMembership.user_id == UserAccount.id)
              & (PropertyMembership.property_id == conv.property_id))
        .where(StaffConversationParticipant.conversation_id == conv.id)
    ).all()
    return [StaffParticipantOut(user_id=u.id, first_name=u.first_name, last_name=u.last_name,
                                avatar_url=u.avatar_url, role=m.role, department_id=m.department_id)
            for u, m in rows]


def _out(db: Session, conv: StaffConversation, viewer_user_id: str) -> StaffConversationOut:
    participants = _participants_out(db, conv)
    display_name, avatar_url, other_user_id = _display(conv, participants, viewer_user_id)
    last = db.scalar(select(StaffMessage).where(StaffMessage.conversation_id == conv.id)
                     .order_by(StaffMessage.created_at.desc(), StaffMessage.id.desc()).limit(1))
    if last is not None:
        preview = last.body.strip() if last.body else ("Sent a photo" if last.photo_data else None)
    else:
        preview = None
    participant_row = db.scalar(select(StaffConversationParticipant).where(
        StaffConversationParticipant.conversation_id == conv.id,
        StaffConversationParticipant.user_id == viewer_user_id))
    last_read = participant_row.last_read_at if participant_row else None
    unread = bool(conv.last_message_at and (last_read is None or conv.last_message_at > last_read))
    return StaffConversationOut(
        id=conv.id, kind=conv.kind, name=conv.name, avatar_url=conv.avatar_url,
        display_name=display_name, other_user_id=other_user_id, participants=participants,
        last_message_at=conv.last_message_at, last_message_preview=preview, unread=unread,
        created_at=conv.created_at, updated_at=conv.updated_at)


def list_conversations_for_user(db: Session, property_id: str,
                                user_id: str) -> list[StaffConversationOut]:
    all_conv = get_or_create_all_conversation(db, property_id)
    ensure_participant(db, all_conv.id, user_id)
    rows = db.scalars(
        select(StaffConversation)
        .join(StaffConversationParticipant,
             StaffConversationParticipant.conversation_id == StaffConversation.id)
        .where(StaffConversation.property_id == property_id,
               StaffConversationParticipant.user_id == user_id)
    ).all()
    out = [_out(db, c, user_id) for c in rows]
    out.sort(key=lambda c: c.last_message_at or c.created_at, reverse=True)
    return out


def detail(db: Session, property_id: str, conversation_id: str,
          viewer_user_id: str) -> StaffConversationDetail:
    conv = get_for_participant(db, property_id, conversation_id, viewer_user_id)
    base = _out(db, conv, viewer_user_id)
    rows = db.execute(
        select(StaffMessage, UserAccount)
        .join(UserAccount, UserAccount.id == StaffMessage.author_user_id)
        .where(StaffMessage.conversation_id == conv.id)
        .order_by(StaffMessage.created_at.desc(), StaffMessage.id.desc())
        .limit(MAX_MESSAGES)
    ).all()
    messages = [
        StaffMessageOut(id=m.id, conversation_id=m.conversation_id, author_user_id=m.author_user_id,
                        author_name=f"{u.first_name} {u.last_name}", body=m.body,
                        photo_url=(photo_url(property_id, m.conversation_id, m.id)
                                  if m.photo_content_type else None),
                        created_at=m.created_at)
        for m, u in reversed(rows)
    ]
    return StaffConversationDetail(**base.model_dump(), messages=messages)


def photo_url(property_id: str, conversation_id: str, message_id: str) -> str:
    return f"/api/p/{property_id}/staff-conversations/{conversation_id}/messages/{message_id}/photo"


def send_message(db: Session, property_id: str, conversation_id: str, actor_user_id: str, *,
                 body: str | None = None, photo_content_type: str | None = None,
                 photo_byte_size: int | None = None, photo_data: bytes | None = None) -> StaffMessage:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    body = body.strip() if body else None
    if not body and not photo_data:
        raise ValidationFailed("A message needs text or a photo")
    msg = StaffMessage(conversation_id=conv.id, property_id=property_id,
                       author_user_id=actor_user_id, body=body,
                       photo_content_type=photo_content_type, photo_byte_size=photo_byte_size,
                       photo_data=photo_data)
    db.add(msg)
    conv.last_message_at = clock.now()
    db.flush()
    ensure_participant(db, conv.id, actor_user_id).last_read_at = clock.now()
    audit.record(db, property_id, actor_user_id, "staff_message.sent", "staff_conversation",
                conv.id)
    queue_event(db, property_id, "staff_message.created", {"conversationId": conv.id})
    other_ids = [p.user_id for p in _participants_out(db, conv) if p.user_id != actor_user_id]
    if other_ids:
        sender = db.get(UserAccount, actor_user_id)
        preview = body or "Sent a photo"
        notifications.notify_users(db, property_id, other_ids, "staff_message",
                                   f"{sender.first_name} {sender.last_name}", body=preview,
                                   entity_type="staff_conversation", entity_id=conv.id)
    return msg


def mark_read(db: Session, property_id: str, conversation_id: str, user_id: str) -> None:
    conv = get_for_participant(db, property_id, conversation_id, user_id)
    participant = ensure_participant(db, conv.id, user_id)
    participant.last_read_at = clock.now()


def _assert_group(conv: StaffConversation) -> None:
    if conv.kind != StaffConversationKind.group:
        raise ValidationFailed("Only group conversations can be edited this way")


def update_group(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
                 data: GroupPatch) -> StaffConversation:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    _assert_group(conv)
    if data.name is not None:
        conv.name = data.name.strip()
    if data.avatar_url is not None:
        conv.avatar_url = data.avatar_url
    db.flush()
    queue_event(db, property_id, "staff_conversation.updated", {"id": conv.id})
    return conv


def add_participants(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
                     data: AddParticipantsRequest) -> StaffConversation:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    _assert_group(conv)
    for uid in data.user_ids:
        _assert_member(db, property_id, uid)
        ensure_participant(db, conv.id, uid)
    queue_event(db, property_id, "staff_conversation.updated", {"id": conv.id})
    return conv


def remove_participant(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
                       target_user_id: str) -> StaffConversation:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    _assert_group(conv)
    row = db.scalar(select(StaffConversationParticipant).where(
        StaffConversationParticipant.conversation_id == conv.id,
        StaffConversationParticipant.user_id == target_user_id))
    if row is not None:
        db.delete(row)
        db.flush()
    queue_event(db, property_id, "staff_conversation.updated", {"id": conv.id})
    return conv


def directory(db: Session, property_id: str, viewer_user_id: str) -> list[StaffDirectoryEntryOut]:
    rows = db.execute(
        select(UserAccount, PropertyMembership, Department)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .outerjoin(Department, Department.id == PropertyMembership.department_id)
        .where(PropertyMembership.property_id == property_id, UserAccount.id != viewer_user_id)
        .order_by(UserAccount.first_name, UserAccount.last_name)
    ).all()
    return [StaffDirectoryEntryOut(user_id=u.id, first_name=u.first_name, last_name=u.last_name,
                                   avatar_url=u.avatar_url, role=m.role,
                                   department_id=m.department_id,
                                   department_name=d.name if d else None) for u, m, d in rows]
