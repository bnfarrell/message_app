### Task 13: SLA sweep and snooze wake (§11.1 #8)

**Files:**
- Create: `server/app/queue/handlers/sla.py`, `server/app/queue/handlers/snooze.py`, `server/tests/test_sla.py`

**Interfaces:**
- Produces: handlers `sla.sweep` (recurring 30 s) and `snooze.wake` (recurring 60 s); `sla.sweep_once(db) -> int` and `snooze.wake_once(db) -> int` for direct use in tests.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_sla.py`:
```python
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.models import Conversation, Notification
from app.queue.handlers.sla import sweep_once
from app.queue.handlers.snooze import wake_once
from app.schemas.enums import ConversationStatus
from tests.factories import inbound


def test_overdue_conversation_notifies_assignee_once(app, fx, client, database, login, events):
    """§11.1 #8"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        c.assigned_user_id = fx.agent_a.id
        cid = c.id
    with database.session() as db:
        assert sweep_once(db) == 0  # not yet due
    clock.advance(minutes=15, seconds=1)
    with database.session() as db:
        assert sweep_once(db) == 1
    with database.session() as db:
        assert sweep_once(db) == 0  # notified only once
        n = db.scalars(select(Notification).where(Notification.type == "sla.breach")).all()
        assert len(n) == 1 and n[0].user_id == fx.agent_a.id and n[0].entity_id == cid
    staff = login("agent@hvh.test")
    assert {r["id"] for r in staff.get(f"/api/p/{fx.property_a.id}/conversations?filter=overdue").get_json()} == {cid}
    assert any(e.type == "conversation.updated" and e.payload["id"] == cid for e in events)


def test_overdue_unassigned_conversation_notifies_front_desk(app, fx, client, database):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "hello")
    clock.advance(minutes=16)
    with database.session() as db:
        sweep_once(db)
        targets = sorted(n.user_id for n in db.scalars(select(Notification).where(Notification.type == "sla.breach")).all())
    assert targets == sorted([fx.agent_a.id, fx.agent_a2.id])


def test_reply_clears_the_breach_and_a_new_inbound_restarts_it(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))
    clock.advance(minutes=16)
    with database.session() as db:
        assert sweep_once(db) == 1
    login("agent@hvh.test").post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages", json={"body": "hi"})
    with database.session() as db:
        c = db.get(Conversation, cid)
        assert c.sla_due_at is None and c.sla_breach_notified_at is None
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "two")
    clock.advance(minutes=16)
    with database.session() as db:
        assert sweep_once(db) == 1


def test_snooze_wake_reopens_due_conversations(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        c.status = ConversationStatus.snoozed
        c.snoozed_until = clock.now() + timedelta(minutes=30)
        cid = c.id
    with database.session() as db:
        assert wake_once(db) == 0
    clock.advance(minutes=31)
    with database.session() as db:
        assert wake_once(db) == 1
        c = db.get(Conversation, cid)
        assert c.status == ConversationStatus.open and c.snoozed_until is None


def test_recurring_jobs_are_registered(app):
    from app.queue import jobs

    assert jobs.RECURRING["sla.sweep"] == 30 and jobs.RECURRING["snooze.wake"] == 60
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_sla.py -q`
Expected: FAIL with `ModuleNotFoundError: app.queue.handlers.sla`.

- [ ] **Step 3: Write the handlers**

`server/app/queue/handlers/sla.py`:
```python
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
```

`server/app/queue/handlers/snooze.py`:
```python
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
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): SLA breach sweep and snooze wake jobs"
```

---

