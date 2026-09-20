## Task 5: Create an entry — validation, mention fan-out, ack snapshot

**Files:**
- Modify: `server/app/domain/log.py`, `server/app/domain/users.py`
- Test: `server/tests/test_log_api.py` (new file, domain-level tests for now)

**Interfaces:**
- Consumes: `shift_for` (Task 2); `CreateLogEntryRequest`, `MentionRef` (Task 4); the models (Task 1)
- Produces:
  - `app.domain.users.active_members_of_department(db, property_id, department_id) -> list[str]`
  - `app.domain.log.create(db, property_id, author_user_id, data: CreateLogEntryRequest, photo: tuple[bytes, str] | None = None) -> LogEntry`
  - `app.domain.log.resolve_audience(db, property_id, refs: list[MentionRef]) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_log_api.py`:

```python
"""Hotel log (spec §3, §4, §6). Domain-level here; route-level assertions arrive in Task 8."""
import pytest

from app.domain import log as log_domain
from app.errors import ValidationFailed
from app.models import LogEntry, LogEntryMention, Notification, UserAccount
from app.schemas.enums import MentionTargetType, Shift, UserStatus
from app.schemas.log import CreateLogEntryRequest, MentionRef


def _req(**kw):
    kw.setdefault("body", "Handover note.")
    return CreateLogEntryRequest(**kw)


def test_create_stores_shift_and_mentions_in_order(database, fx):
    with database.session() as db:
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(mentions=[MentionRef(type=MentionTargetType.department,
                                      id=fx.dept_housekeeping.id),
                           MentionRef(type=MentionTargetType.user, id=fx.engineer_a.id)]),
        )
        db.flush()
        # conftest freezes 2026-09-10 12:00 UTC = 08:00 in America/New_York.
        assert entry.shift == Shift.am
        rows = db.scalars(
            select(LogEntryMention)
            .where(LogEntryMention.log_entry_id == entry.id)
            .order_by(LogEntryMention.position)
        ).all()
        assert [(r.type, r.target_id) for r in rows] == [
            (MentionTargetType.department, fx.dept_housekeeping.id),
            (MentionTargetType.user, fx.engineer_a.id),
        ]


def test_department_mention_notifies_each_member_once_and_never_the_author(database, fx):
    with database.session() as db:
        # The author is in front desk; mention front desk AND the author directly.
        log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(mentions=[MentionRef(type=MentionTargetType.department,
                                      id=fx.dept_front_desk.id),
                           MentionRef(type=MentionTargetType.user, id=fx.agent_a2.id)]),
        )
        db.flush()
        rows = db.scalars(select(Notification)
                          .where(Notification.type == "log.mention")).all()
        recipients = [n.user_id for n in rows]
        assert fx.agent_a.id not in recipients, "author must never be notified"
        assert recipients.count(fx.agent_a2.id) == 1, "mentioned twice, notified once"


def test_ack_expected_snapshots_active_department_members_excluding_author(database, fx):
    from app.models import PropertyMembership

    with database.session() as db:
        # A second active housekeeper, so the assertion below is about a real denominator
        # and not vacuously true of an always-empty list.
        other = db.scalar(select(PropertyMembership).where(
            PropertyMembership.user_id == fx.agent_a2.id,
            PropertyMembership.property_id == fx.property_a.id))
        other.department_id = fx.dept_housekeeping.id
        db.flush()
        entry = log_domain.create(
            db, fx.property_a.id, fx.housekeeper_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.department,
                                          id=fx.dept_housekeeping.id)]),
        )
        db.flush()
        assert fx.agent_a2.id in entry.ack_expected, "an active member must be expected"
        assert fx.housekeeper_a.id not in entry.ack_expected, "the author must not be"
        assert entry.requires_ack is True


def test_disabled_users_are_excluded_from_the_snapshot(database, fx):
    with database.session() as db:
        db.get(UserAccount, fx.engineer_a.id).status = UserStatus.disabled
        db.flush()
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.department,
                                          id=fx.dept_engineering.id)]),
        )
        db.flush()
        assert fx.engineer_a.id not in entry.ack_expected


def test_an_empty_resolved_audience_downgrades_requires_ack(database, fx):
    with database.session() as db:
        # housekeeper_a is the only active housekeeping member, and is the author.
        entry = log_domain.create(
            db, fx.property_a.id, fx.housekeeper_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.user,
                                          id=fx.housekeeper_a.id)]),
        )
        db.flush()
        assert entry.requires_ack is False
        assert entry.ack_expected == []


def test_a_cross_property_mention_is_rejected(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed):
            log_domain.create(
                db, fx.property_a.id, fx.agent_a.id,
                _req(mentions=[MentionRef(type=MentionTargetType.user, id=fx.agent_b.id)]),
            )


def test_a_cross_property_department_tag_is_rejected(database, fx):
    with database.session() as db:
        other = fx.property_b.id
        dept_b = db.scalar(select(Department.id).where(Department.property_id == other))
        with pytest.raises(ValidationFailed):
            log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                              _req(department_id=dept_b))
```

Add `from sqlalchemy import select` and `from app.models import Department` to the imports.

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q`
Expected: FAIL with `AttributeError: module 'app.domain.log' has no attribute 'create'`

- [ ] **Step 3: Add the active-members helper**

`app.domain.users.members_of_department` does not filter on status. Rather than change it and its existing callers, add a sibling in `server/app/domain/users.py`:

```python
def active_members_of_department(db: Session, property_id: str,
                                 department_id: str) -> list[str]:
    """Like members_of_department, but only accounts that can actually act.

    The hotel log's acknowledgement denominator uses this: a disabled account can never
    acknowledge, so counting it would make the denominator permanently unreachable
    (hotel-log spec §3.2).
    """
    return list(
        db.scalars(
            select(PropertyMembership.user_id)
            .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
            .where(
                PropertyMembership.property_id == property_id,
                PropertyMembership.department_id == department_id,
                UserAccount.status == UserStatus.active,
            )
        ).all()
    )
```

Add `UserStatus` to that module's imports from `app.schemas.enums` if it is not already imported.

- [ ] **Step 4: Implement create**

Append to `server/app/domain/log.py` (add the imports at the top of the file):

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, notifications
from app.domain.users import active_members_of_department
from app.errors import ValidationFailed
from app.models import (
    Conversation,
    Department,
    LogEntry,
    LogEntryMention,
    LogEntryPhoto,
    PropertyMembership,
    UserAccount,
    WorkOrder,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import MentionTargetType
from app.schemas.log import CreateLogEntryRequest, MentionRef


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

    expected = [uid for uid in resolve_audience(db, property_id, data.ack_audience)
                if uid != author_user_id] if data.requires_ack else []

    entry = LogEntry(
        property_id=property_id,
        author_user_id=author_user_id,
        department_id=data.department_id,
        shift=shift_for(prop, clock.now()),
        body=data.body.strip(),
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
```

Add `Property` and `UserStatus` to the imports at the top of `app/domain/log.py`.

- [ ] **Step 5: Run to verify they pass**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 6: Full suite and lint**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .`
Expected: all green, lint clean.

- [ ] **Step 7: Commit**

```bash
git add server/app/domain/log.py server/app/domain/users.py server/tests/test_log_api.py
git commit -m "feat(server): create hotel log entries with mention fan-out and ack snapshot"
```

---

