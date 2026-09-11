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
    overdue = staff.get(f"/api/p/{fx.property_a.id}/conversations?filter=overdue").get_json()
    assert {r["id"] for r in overdue} == {cid}
    assert any(e.type == "conversation.updated" and e.payload["id"] == cid for e in events)


def test_overdue_unassigned_conversation_notifies_front_desk(app, fx, client, database):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "hello")
    clock.advance(minutes=16)
    with database.session() as db:
        sweep_once(db)
        breaches = db.scalars(select(Notification).where(Notification.type == "sla.breach")).all()
        targets = sorted(n.user_id for n in breaches)
    assert targets == sorted([fx.agent_a.id, fx.agent_a2.id])


def test_reply_clears_the_breach_and_a_new_inbound_restarts_it(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(
            Conversation.guest_id == fx.guest_inhouse_a.id))
    clock.advance(minutes=16)
    with database.session() as db:
        assert sweep_once(db) == 1
    login("agent@hvh.test").post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                                 json={"body": "hi"})
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
