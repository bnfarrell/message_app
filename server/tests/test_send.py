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


def test_send_rejects_when_digital_asset_link_pushes_body_over_length(app, fx, client, database):
    """The short link is appended before the length is enforced, not after (review finding 2)."""
    import pytest

    from app.errors import ValidationFailed
    from app.models import DigitalAsset

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    cid = _conversation_id(database, fx)
    with database.session() as db:
        asset = DigitalAsset(property_id=fx.property_a.id, name="Spa Menu",
                             url="https://example.test/spa", short_code="spa1")
        db.add(asset)
        db.flush()
        asset_id = asset.id
    body = "x" * (messages.MAX_BODY - 5)  # + " /a/spa1" (8 chars) pushes just over MAX_BODY
    with database.session() as db, pytest.raises(ValidationFailed):
        messages.send(db, fx.property_a.id, cid, body, author_user_id=fx.agent_a.id,
                      digital_asset_id=asset_id)


def test_system_send_does_not_clear_sla_or_record_first_response(app, fx, client, database):
    """Only a staff reply should satisfy the SLA clock or first-response timer (finding 3)."""
    from app.schemas.enums import AuthorType

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _conversation_id(database, fx)
    with database.session() as db:
        assert db.get(Conversation, cid).sla_due_at is not None  # sanity: inbound started the SLA
    with database.session() as db:
        messages.send(db, fx.property_a.id, cid, "Automated heads up", author_user_id=None,
                      author_type=AuthorType.system)
        c = db.get(Conversation, cid)
        assert c.sla_due_at is not None  # a system send must not silently satisfy a human SLA
        assert c.first_response_seconds is None


def test_send_audit_survives_a_dirty_caller_session(app, fx, database):
    """Mimics a caller (e.g. inbound.handle) whose outer transaction already flushed rows before a
    rejected send: the audit row must still be written, not deadlock the shared connection
    (review finding 1)."""
    import pytest

    from app.domain import consent
    from app.domain import conversations as conv_domain
    from app.errors import ConsentError
    from app.models import AuditLog, Guest

    with pytest.raises(ConsentError) as ei:
        with database.session() as db:
            guest = db.get(Guest, fx.guest_inhouse_a.id)
            consent.opt_out(db, guest, "sms_keyword")
            conv, _ = conv_domain.find_or_create_for_guest(db, fx.property_a.id, guest)
            messages.record_inbound(db, fx.property_a.id, conv, "already flushed on this session",
                                    "SM-dirty")
            messages.send(db, fx.property_a.id, conv.id, "Hello?", author_user_id=fx.agent_a.id)
    assert ei.value.status == 422 and ei.value.code == "CONSENT_OPTED_OUT"
    with database.session() as db:
        assert db.scalar(select(Message).where(Message.direction == Direction.outbound)) is None
        assert db.scalar(select(AuditLog).where(
            AuditLog.action == "message.rejected_opted_out")) is not None
