from sqlalchemy import select

from app import clock
from app.domain import messages
from app.models import Conversation, Message
from app.schemas.enums import DeliveryStatus, Direction
from tests.factories import inbound


def _conversation_id(database, fx):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))


def test_send_queues_message_clears_sla_and_records_first_response(app, fx, client, database, events):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _conversation_id(database, fx)
    clock.advance(minutes=3)
    with database.session() as db:
        m = messages.send(db, fx.property_a.id, cid, "On it, Sarah.", author_user_id=fx.agent_a.id)
        assert m.delivery_status == DeliveryStatus.queued and m.direction == Direction.outbound
        c = db.get(Conversation, cid)
        assert c.sla_due_at is None
        assert c.first_response_seconds == 180
        assert c.last_staff_message_at == clock.now()
    assert any(e.type == "message.created" and e.payload["body"] == "On it, Sarah." for e in events)
    from app.models import Job

    with database.session() as db:
        assert db.scalar(select(Job).where(Job.type == "outbound.send")) is not None


def test_send_via_api_requires_reply_capability(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _conversation_id(database, fx)
    corporate = login("corporate@hvh.test")
    assert corporate.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                          json={"body": "x"}).status_code == 403
    agent = login("agent@hvh.test")
    res = agent.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages", json={"body": "x"})
    assert res.status_code == 201
    assert res.get_json()["deliveryStatus"] == "queued"


def test_first_response_is_recorded_only_once(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    cid = _conversation_id(database, fx)
    clock.advance(minutes=2)
    with database.session() as db:
        messages.send(db, fx.property_a.id, cid, "a", author_user_id=fx.agent_a.id)
    clock.advance(minutes=10)
    with database.session() as db:
        messages.send(db, fx.property_a.id, cid, "b", author_user_id=fx.agent_a.id)
        assert db.get(Conversation, cid).first_response_seconds == 120


def test_send_rejects_over_length(app, fx, client, database):
    import pytest

    from app.errors import ValidationFailed

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    cid = _conversation_id(database, fx)
    with database.session() as db, pytest.raises(ValidationFailed):
        messages.send(db, fx.property_a.id, cid, "x" * 1601, author_user_id=fx.agent_a.id)
