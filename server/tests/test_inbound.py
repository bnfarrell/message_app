from sqlalchemy import select

from app.models import AuditLog, Conversation, Guest, Message
from app.schemas.enums import ConversationStatus, DeliveryStatus, Direction, SmsConsentStatus
from tests.factories import inbound


def test_unknown_number_creates_guest_and_conversation(app, fx, client, database, events):
    """§11.1 #1"""
    res = inbound(client, fx, "+15550142290", "Hi, arriving around 9pm tonight, is that ok?")
    assert res.status_code == 204
    with database.session() as db:
        g = db.scalar(select(Guest).where(Guest.phone_e164 == "+15550142290"))
        assert g.property_id == fx.property_a.id
        assert g.sms_consent_status == SmsConsentStatus.opted_in
        assert g.sms_consent_source == "inbound_sms"
        c = db.scalar(select(Conversation).where(Conversation.guest_id == g.id))
        assert c.status == ConversationStatus.open and c.stay_id is None
        assert c.sla_due_at is not None and c.last_guest_message_at is not None
        m = db.scalar(select(Message).where(Message.conversation_id == c.id))
        assert m.direction == Direction.inbound and m.body.startswith("Hi, arriving")
    assert [e.type for e in events if e.type.startswith("conversation.")] == ["conversation.created"]
    assert any(e.type == "message.created" for e in events)


def test_known_in_house_guest_attaches_stay(app, fx, client, database):
    """§11.1 #2"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "The AC in our room isn't working")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        assert c.stay_id == fx.stay_inhouse_a.id


def test_second_message_reuses_open_conversation(app, fx, client, database):
    inbound(client, fx, "+15550142290", "one")
    inbound(client, fx, "+15550142290", "two")
    with database.session() as db:
        assert db.scalar(select(Conversation).where(
            Conversation.property_id == fx.property_a.id)) is not None
        convs = db.scalars(select(Conversation).where(Conversation.property_id == fx.property_a.id)).all()
        assert len(convs) == 1
        assert len(db.scalars(select(Message).where(Message.conversation_id == convs[0].id)).all()) == 2


def test_archived_conversation_reopens_on_inbound(app, fx, client, database):
    from app import clock

    inbound(client, fx, "+15550142290", "one")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.property_id == fx.property_a.id))
        c.status = ConversationStatus.archived
        c.archived_at = clock.now()
    inbound(client, fx, "+15550142290", "two")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.property_id == fx.property_a.id))
        assert c.status == ConversationStatus.open and c.archived_at is None


def test_duplicate_provider_sid_is_idempotent(app, fx, client, database):
    inbound(client, fx, "+15550142290", "one", sid="SM-dup")
    inbound(client, fx, "+15550142290", "one", sid="SM-dup")
    with database.session() as db:
        assert len(db.scalars(select(Message)).all()) == 1


def test_stop_opts_out_sends_one_confirmation_and_blocks_sends(app, fx, client, database, worker, login):
    """§11.1 #5"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "STOP")
    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        assert g.sms_consent_status == SmsConsentStatus.opted_out
        c = db.scalar(select(Conversation).where(Conversation.guest_id == g.id))
        msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.sent_at)).all()
        assert [m.direction for m in msgs] == [Direction.inbound, Direction.outbound]
        assert "unsubscribed" in msgs[1].body.lower() and "START" in msgs[1].body
        assert c.sla_due_at is None  # keyword messages do not start an SLA
    staff = login("agent@hvh.test")
    res = staff.post(f"/api/p/{fx.property_a.id}/conversations/{c.id}/messages", json={"body": "Hello?"})
    assert res.status_code == 422
    assert res.get_json()["error"]["code"] == "CONSENT_OPTED_OUT"
    with database.session() as db:
        assert len(db.scalars(select(Message).where(Message.direction == Direction.outbound)).all()) == 1
        actions = [a.action for a in db.scalars(select(AuditLog)).all()]
        assert "message.rejected_opted_out" in actions and "consent.opted_out" in actions
    # START re-enables
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "START")
    with database.session() as db:
        assert db.get(Guest, fx.guest_inhouse_a.id).sms_consent_status == SmsConsentStatus.opted_in


def test_help_replies_with_property_help_text(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "HELP")
    with database.session() as db:
        out = db.scalar(select(Message).where(Message.direction == Direction.outbound))
        assert "555 0100" in out.body


def test_card_numbers_are_redacted_before_storage(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "charge it to 4242 4242 4242 4242 pls")
    with database.session() as db:
        m = db.scalar(select(Message).where(Message.direction == Direction.inbound))
        assert m.redacted is True and "4242 4242 4242 4242" not in m.body and m.body.endswith("4242 pls")


def test_webhook_rejects_bad_secret_and_unknown_property_number(app, fx, client):
    res = client.post("/api/hooks/sms/inbound", data={"From": "+15550142290", "To": fx.property_a.sms_number,
                                                     "Body": "x", "MessageSid": "SM1"},
                      headers={"X-Mock-Secret": "wrong"})
    assert res.status_code == 401
    res = inbound(client, fx, "+15550142290", "x", to="+19999999999")
    assert res.status_code == 404


def test_inbound_notifies_front_desk_when_unassigned(app, fx, client, database):
    from app.models import Notification

    inbound(client, fx, "+15550142290", "hello")
    with database.session() as db:
        targets = sorted(n.user_id for n in db.scalars(select(Notification)).all())
    assert targets == sorted([fx.agent_a.id, fx.agent_a2.id])
