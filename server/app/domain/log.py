from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, notifications
from app.domain.users import active_members_of_department
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import (
    Conversation,
    Department,
    LogEntry,
    LogEntryAck,
    LogEntryMention,
    LogEntryPhoto,
    Property,
    PropertyMembership,
    UserAccount,
    WorkOrder,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import MentionTargetType, Shift, UserStatus
from app.schemas.log import (
    FEED_PAGE_SIZE,
    CreateLogEntryRequest,
    LogAckOut,
    LogEntryOut,
    LogFeedOut,
    LogFeedQuery,
    LogMentionableOut,
    LogMentionOut,
    LogPersonOut,
    MentionRef,
)

# Spec §3.3. Overridable per property via settings["shift_boundaries"].
DEFAULT_SHIFT_BOUNDARIES = {"am": "07:00", "pm": "15:00", "overnight": "23:00"}


def _boundary(raw: dict, key: str) -> time:
    value = raw.get(key) or DEFAULT_SHIFT_BOUNDARIES[key]
    hour, _, minute = value.partition(":")
    return time(int(hour), int(minute))


def shift_for(prop: Property, at: datetime) -> Shift:
    """Which shift `at` falls in, on the property's own clock.

    Computed once at creation and then stored, so editing the boundaries later does not
    retroactively relabel history (spec §3.3). Overnight is the window that wraps midnight,
    which is why this is a three-way comparison rather than a sorted bisect.
    """
    if at.tzinfo is None:
        raise ValueError("shift_for requires an aware datetime")
    raw = (prop.settings or {}).get("shift_boundaries") or {}
    am, pm, overnight = (_boundary(raw, k) for k in ("am", "pm", "overnight"))
    local = at.astimezone(ZoneInfo(prop.timezone)).time()
    if am <= local < pm:
        return Shift.am
    if pm <= local < overnight:
        return Shift.pm
    return Shift.overnight


def _assert_member(db: Session, property_id: str, user_id: str) -> None:
    if not db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.property_id == property_id,
            PropertyMembership.user_id == user_id)):
        raise ValidationFailed("That person is not a member of this property")


def _assert_department(db: Session, property_id: str, department_id: str) -> None:
    if not db.scalar(select(Department.id).where(Department.property_id == property_id,
                                                 Department.id == department_id)):
        raise ValidationFailed("That department is not part of this property")


def _validate_refs(db: Session, property_id: str, refs: list[MentionRef]) -> None:
    for ref in refs:
        if ref.type == MentionTargetType.user:
            _assert_member(db, property_id, ref.id)
        else:
            _assert_department(db, property_id, ref.id)


def resolve_audience(db: Session, property_id: str, refs: list[MentionRef]) -> list[str]:
    """Flatten mention refs to concrete active user ids, de-duplicated, order preserved."""
    out: list[str] = []
    for ref in refs:
        if ref.type == MentionTargetType.user:
            out.append(ref.id)
        else:
            out.extend(active_members_of_department(db, property_id, ref.id))
    active = set(db.scalars(
        select(UserAccount.id).where(UserAccount.id.in_(out or [""]),
                                     UserAccount.status == UserStatus.active)).all())
    return [uid for uid in dict.fromkeys(out) if uid in active]


def create(db: Session, property_id: str, author_user_id: str,
           data: CreateLogEntryRequest,
           photo: tuple[bytes, str] | None = None) -> LogEntry:
    prop = db.get(Property, property_id)
    if data.department_id:
        _assert_department(db, property_id, data.department_id)
    _validate_refs(db, property_id, data.mentions)
    _validate_refs(db, property_id, data.ack_audience)
    if data.linked_work_order_id and not db.scalar(select(WorkOrder.id).where(
            WorkOrder.id == data.linked_work_order_id,
            WorkOrder.property_id == property_id)):
        raise ValidationFailed("That work order is not part of this property")
    if data.linked_conversation_id and not db.scalar(select(Conversation.id).where(
            Conversation.id == data.linked_conversation_id,
            Conversation.property_id == property_id)):
        raise ValidationFailed("That conversation is not part of this property")

    body = data.body.strip()
    if not body:
        raise ValidationFailed("A log entry needs a body")

    expected = [uid for uid in resolve_audience(db, property_id, data.ack_audience)
                if uid != author_user_id] if data.requires_ack else []

    entry = LogEntry(
        property_id=property_id,
        author_user_id=author_user_id,
        department_id=data.department_id,
        shift=shift_for(prop, clock.now()),
        body=body,
        # An audience that resolves to nobody would render "0 of 0 acknowledged", which is
        # not a claim about anything (spec §3.2).
        requires_ack=bool(expected),
        ack_expected=expected,
        linked_work_order_id=data.linked_work_order_id,
        linked_conversation_id=data.linked_conversation_id,
    )
    db.add(entry)
    db.flush()

    for position, ref in enumerate(data.mentions):
        db.add(LogEntryMention(log_entry_id=entry.id, property_id=property_id,
                               type=ref.type, target_id=ref.id, position=position))
    if photo is not None:
        body_bytes, content_type = photo
        db.add(LogEntryPhoto(log_entry_id=entry.id, property_id=property_id,
                             uploaded_by_user_id=author_user_id,
                             content_type=content_type, byte_size=len(body_bytes),
                             data=body_bytes))
    db.flush()

    author = db.get(UserAccount, author_user_id)
    mentioned = [uid for uid in resolve_audience(db, property_id, data.mentions)
                 if uid != author_user_id]
    notifications.notify_users(
        db, property_id, mentioned, "log.mention",
        f"{author.first_name} mentioned you in the hotel log",
        body=entry.body[:140], entity_type="log_entry", entity_id=entry.id)
    # Somebody asked to acknowledge who was not also mentioned still needs telling.
    notifications.notify_users(
        db, property_id, [uid for uid in expected if uid not in set(mentioned)],
        "log.ack_requested",
        f"{author.first_name} needs you to acknowledge a log entry",
        body=entry.body[:140], entity_type="log_entry", entity_id=entry.id)

    audit.record(db, property_id, author_user_id, "log_entry.created", "log_entry", entry.id,
                 after={"shift": entry.shift.value, "requires_ack": entry.requires_ack})
    queue_event(db, property_id, "log.entry.created", {"id": entry.id})
    return entry


def photo_url(property_id: str, entry_id: str) -> str:
    return f"/api/p/{property_id}/log-entries/{entry_id}/photo"


def _encode_cursor(entry: LogEntry) -> str:
    return f"{entry.created_at.isoformat()}|{entry.id}"


def _decode_cursor(raw: str) -> tuple[datetime, str]:
    created, _, entry_id = raw.partition("|")
    try:
        return datetime.fromisoformat(created), entry_id
    except ValueError as e:
        raise ValidationFailed("Invalid cursor") from e


def _viewer_department_ids(db: Session, property_id: str, user_id: str) -> list[str]:
    return list(db.scalars(select(PropertyMembership.department_id).where(
        PropertyMembership.property_id == property_id,
        PropertyMembership.user_id == user_id,
        PropertyMembership.department_id.is_not(None))).all())


def _to_out(db: Session, entries: list[LogEntry], viewer_user_id: str) -> list[LogEntryOut]:
    """One pass over a page of entries, batching the joins the cards need."""
    if not entries:
        return []
    ids = [e.id for e in entries]
    property_id = entries[0].property_id
    # Both lookups are property-scoped. An unscoped SELECT over user_account cannot leak
    # here (only ids present on this property's entries are read back), but it loads the
    # whole table on every feed page and is a standing trap in a property-isolated codebase.
    names: dict[str, str] = {}
    avatars: dict[str, str | None] = {}
    for uid, first, last, avatar in db.execute(
            select(UserAccount.id, UserAccount.first_name, UserAccount.last_name,
                   UserAccount.avatar_url)
            .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
            .where(PropertyMembership.property_id == property_id)).all():
        names[uid] = f"{first} {last}"
        avatars[uid] = avatar
    dept_names = dict(db.execute(
        select(Department.id, Department.name)
        .where(Department.property_id == property_id)).all())

    mentions: dict[str, list[LogMentionOut]] = {i: [] for i in ids}
    for row in db.scalars(select(LogEntryMention)
                          .where(LogEntryMention.log_entry_id.in_(ids))
                          .order_by(LogEntryMention.position)).all():
        display = (names.get(row.target_id) if row.type == MentionTargetType.user
                   else dept_names.get(row.target_id)) or "Unknown"
        mentions[row.log_entry_id].append(
            LogMentionOut(type=row.type, id=row.target_id, display_name=display))

    acks: dict[str, list[LogAckOut]] = {i: [] for i in ids}
    for row in db.scalars(select(LogEntryAck)
                          .where(LogEntryAck.log_entry_id.in_(ids))
                          .order_by(LogEntryAck.acknowledged_at)).all():
        acks[row.log_entry_id].append(
            LogAckOut(user_id=row.user_id, name=names.get(row.user_id, "Unknown"),
                      acknowledged_at=row.acknowledged_at))

    has_photo = set(db.scalars(select(LogEntryPhoto.log_entry_id)
                               .where(LogEntryPhoto.log_entry_id.in_(ids))).all())

    out: list[LogEntryOut] = []
    for e in entries:
        acked = {a.user_id for a in acks[e.id]}
        expected = list(e.ack_expected or [])
        out.append(LogEntryOut(
            id=e.id, created_at=e.created_at,
            author_user_id=e.author_user_id,
            author_name=names.get(e.author_user_id, "Unknown"),
            author_avatar_url=avatars.get(e.author_user_id),
            department_id=e.department_id,
            department_name=dept_names.get(e.department_id) if e.department_id else None,
            shift=e.shift, body=e.body, mentions=mentions[e.id],
            pinned=e.pinned, pinned_by_user_id=e.pinned_by_user_id, pinned_at=e.pinned_at,
            requires_ack=e.requires_ack, ack_expected_count=len(expected),
            acks=acks[e.id],
            outstanding=[LogPersonOut(user_id=u, name=names.get(u, "Unknown"))
                         for u in expected if u not in acked],
            acked_by_me=viewer_user_id in acked,
            can_ack=viewer_user_id in expected and viewer_user_id not in acked,
            photo_url=photo_url(e.property_id, e.id) if e.id in has_photo else None,
            linked_work_order_id=e.linked_work_order_id,
            linked_conversation_id=e.linked_conversation_id,
        ))
    return out


def feed(db: Session, property_id: str, viewer_user_id: str, query: LogFeedQuery) -> LogFeedOut:
    stmt = select(LogEntry).where(LogEntry.property_id == property_id)
    if query.shift:
        stmt = stmt.where(LogEntry.shift == query.shift)
    if query.department_id:
        stmt = stmt.where(LogEntry.department_id == query.department_id)
    if query.from_:
        stmt = stmt.where(LogEntry.created_at >= _day_bound(db, property_id, query.from_, False))
    if query.to:
        stmt = stmt.where(LogEntry.created_at < _day_bound(db, property_id, query.to, True))
    if query.mentioning_me:
        dept_ids = _viewer_department_ids(db, property_id, viewer_user_id)
        stmt = stmt.where(select(LogEntryMention.id).where(
            LogEntryMention.log_entry_id == LogEntry.id,
            or_(and_(LogEntryMention.type == MentionTargetType.user,
                     LogEntryMention.target_id == viewer_user_id),
                and_(LogEntryMention.type == MentionTargetType.department,
                     LogEntryMention.target_id.in_(dept_ids or [""])))).exists())
    if query.cursor:
        created, entry_id = _decode_cursor(query.cursor)
        stmt = stmt.where(tuple_(LogEntry.created_at, LogEntry.id) < (created, entry_id))

    rows = list(db.scalars(
        stmt.order_by(LogEntry.created_at.desc(), LogEntry.id.desc())
        .limit(FEED_PAGE_SIZE + 1)).all())
    next_cursor = _encode_cursor(rows[FEED_PAGE_SIZE - 1]) if len(rows) > FEED_PAGE_SIZE else None
    rows = rows[:FEED_PAGE_SIZE]

    pinned_rows = list(db.scalars(
        select(LogEntry)
        .where(LogEntry.property_id == property_id, LogEntry.pinned.is_(True))
        .order_by(LogEntry.created_at.desc())).all())

    return LogFeedOut(pinned=_to_out(db, pinned_rows, viewer_user_id),
                      entries=_to_out(db, rows, viewer_user_id),
                      next_cursor=next_cursor)


def get(db: Session, property_id: str, entry_id: str) -> LogEntry:
    entry = db.get(LogEntry, entry_id)
    if entry is None or entry.property_id != property_id:
        raise NotFound("Log entry not found")
    return entry


def get_out(db: Session, property_id: str, viewer_user_id: str, entry_id: str) -> LogEntryOut:
    return _to_out(db, [get(db, property_id, entry_id)], viewer_user_id)[0]


def acknowledge(db: Session, property_id: str, user_id: str, entry_id: str) -> LogEntry:
    entry = get(db, property_id, entry_id)
    if user_id not in (entry.ack_expected or []):
        # An acknowledgement from somebody who was never asked is noise in the audit
        # trail, so it is refused rather than silently recorded (spec §5).
        raise Forbidden("You were not asked to acknowledge this entry")
    existing = db.scalar(select(LogEntryAck).where(
        LogEntryAck.log_entry_id == entry.id, LogEntryAck.user_id == user_id))
    if existing is not None:
        return entry
    db.add(LogEntryAck(log_entry_id=entry.id, property_id=property_id, user_id=user_id,
                       acknowledged_at=clock.now()))
    db.flush()
    audit.record(db, property_id, user_id, "log_entry.acknowledged", "log_entry", entry.id)
    queue_event(db, property_id, "log.entry.updated", {"id": entry.id})
    return entry


def set_pinned(db: Session, property_id: str, user_id: str, entry_id: str,
               pinned: bool) -> LogEntry:
    entry = get(db, property_id, entry_id)
    if entry.pinned == pinned:
        return entry
    before = {"pinned": entry.pinned}
    entry.pinned = pinned
    entry.pinned_by_user_id = user_id if pinned else None
    entry.pinned_at = clock.now() if pinned else None
    db.flush()
    audit.record(db, property_id, user_id, "log_entry.pinned" if pinned else
                 "log_entry.unpinned", "log_entry", entry.id,
                 before=before, after={"pinned": pinned})
    queue_event(db, property_id, "log.entry.updated", {"id": entry.id})
    return entry


def _day_bound(db: Session, property_id: str, iso_date: str, exclusive_end: bool) -> datetime:
    """`from`/`to` are dates on the property's clock, not UTC (spec §4.2)."""
    prop = db.get(Property, property_id)
    try:
        day = date.fromisoformat(iso_date)
    except ValueError as e:
        raise ValidationFailed("Dates must be ISO (YYYY-MM-DD)") from e
    if exclusive_end:
        day = day + timedelta(days=1)
    tz = ZoneInfo(prop.timezone)
    return datetime.combine(day, time(0, 0), tzinfo=tz).astimezone(UTC)


def mentionables(db: Session, property_id: str) -> list[LogMentionableOut]:
    """One flat list for the composer's picker: every active member, then every
    department. Ids are what the composer records; display names are presentation only."""
    rows = db.execute(
        select(UserAccount.id, UserAccount.first_name, UserAccount.last_name,
               PropertyMembership.role)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .where(PropertyMembership.property_id == property_id,
               UserAccount.status == UserStatus.active)
        .order_by(UserAccount.first_name, UserAccount.last_name)).all()
    people = [LogMentionableOut(type=MentionTargetType.user, id=uid,
                                display_name=f"{first} {last}", subtitle=role.value)
              for uid, first, last, role in rows]
    dept_rows = db.execute(
        select(Department.id, Department.name)
        .where(Department.property_id == property_id)
        .order_by(Department.name)).all()
    departments = [LogMentionableOut(type=MentionTargetType.department, id=did,
                                     display_name=name, subtitle="Department")
                   for did, name in dept_rows]
    return people + departments


def get_photo(db: Session, property_id: str, entry_id: str) -> tuple[bytes, str]:
    get(db, property_id, entry_id)  # 404s before the blob lookup, and scopes the property
    row = db.scalar(select(LogEntryPhoto)
                    .where(LogEntryPhoto.log_entry_id == entry_id,
                           LogEntryPhoto.property_id == property_id))
    if row is None:
        raise NotFound("No photo on this log entry")
    return row.data, row.content_type
