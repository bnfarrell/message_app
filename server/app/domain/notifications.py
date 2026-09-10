from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.domain.users import members_of_department
from app.models import Department, Notification, PropertyMembership
from app.realtime.broadcast import queue_event
from app.schemas.enums import DepartmentType, Role
from app.schemas.notifications import NotificationOut


def create(db: Session, property_id: str, user_id: str, type: str, title: str, body: str | None = None,
           entity_type: str | None = None, entity_id: str | None = None) -> Notification:
    n = Notification(property_id=property_id, user_id=user_id, type=type, title=title, body=body,
                     entity_type=entity_type, entity_id=entity_id)
    db.add(n)
    db.flush()
    queue_event(db, property_id, "notification.created",
                NotificationOut.model_validate(n).model_dump(mode="json", by_alias=True),
                user_id=user_id)
    return n


def notify_users(db: Session, property_id: str, user_ids: list[str], type: str, title: str,
                 body: str | None = None, entity_type: str | None = None,
                 entity_id: str | None = None) -> list[Notification]:
    return [create(db, property_id, uid, type, title, body, entity_type, entity_id)
            for uid in dict.fromkeys(user_ids)]


def _front_desk_members(db: Session, property_id: str) -> list[str]:
    dept_id = db.scalar(select(Department.id).where(Department.property_id == property_id,
                                                    Department.type == DepartmentType.front_desk))
    return members_of_department(db, property_id, dept_id) if dept_id else []


def _admins(db: Session, property_id: str) -> list[str]:
    return list(db.scalars(select(PropertyMembership.user_id).where(
        PropertyMembership.property_id == property_id, PropertyMembership.role == Role.admin)).all())


def notify_user_or_department(db: Session, property_id: str, *, user_id: str | None,
                              department_id: str | None, type: str, title: str,
                              body: str | None = None, entity_type: str | None = None,
                              entity_id: str | None = None) -> list[Notification]:
    if user_id:
        targets = [user_id]
    elif department_id:
        targets = members_of_department(db, property_id, department_id)
    else:
        targets = []
    if not targets:
        targets = _front_desk_members(db, property_id) or _admins(db, property_id)
    return notify_users(db, property_id, targets, type, title, body, entity_type, entity_id)


def list_for_user(db: Session, property_id: str, user_id: str, unread_only: bool = False,
                  limit: int = 50) -> list[NotificationOut]:
    q = select(Notification).where(Notification.property_id == property_id,
                                   Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = db.scalars(q.order_by(Notification.created_at.desc()).limit(limit)).all()
    return [NotificationOut.model_validate(n) for n in rows]


def unread_count(db: Session, property_id: str, user_id: str) -> int:
    return db.scalar(select(func.count()).select_from(Notification).where(
        Notification.property_id == property_id, Notification.user_id == user_id,
        Notification.read_at.is_(None))) or 0


def mark_read(db: Session, property_id: str, user_id: str, notification_id: str) -> bool:
    n = db.scalar(select(Notification).where(Notification.id == notification_id,
                                             Notification.property_id == property_id,
                                             Notification.user_id == user_id))
    if n is None:
        return False
    if n.read_at is None:
        n.read_at = clock.now()
    return True


def mark_all_read(db: Session, property_id: str, user_id: str) -> int:
    rows = db.scalars(select(Notification).where(Notification.property_id == property_id,
                                                 Notification.user_id == user_id,
                                                 Notification.read_at.is_(None))).all()
    now = clock.now()
    for n in rows:
        n.read_at = now
    return len(rows)
