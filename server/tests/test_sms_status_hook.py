"""POST /api/hooks/sms/status — Twilio's delivery-status callback.

Authenticated through the configured adapter's verify_inbound, so these run against the mock
adapter with its shared secret; the Twilio signature check itself is covered in
test_twilio_sms.py. Status mapping and the forward-only invariant are what is under test here.
"""
import pytest

from app.models import Message
from app.schemas.enums import DeliveryStatus, Direction
from tests.factories import make_conversation, make_message

SID = "SM0123456789abcdef"


def _outbound(database, fx, **overrides) -> str:
    from app.models import Guest

    with database.session() as db:
        guest = db.get(Guest, fx.guest_inhouse_a.id)
        conv = make_conversation(db, fx, guest)
        msg = make_message(db, conv, direction=Direction.outbound, body="Hello",
                           provider_message_id=SID, **overrides)
    return msg.id


def _post(client, data: dict, *, secret: str = "dev"):
    return client.post("/api/hooks/sms/status", data={"MessageSid": SID, **data},
                       headers={"X-Mock-Secret": secret})


@pytest.mark.parametrize("twilio_status,expected", [
    ("sent", DeliveryStatus.sent),
    ("delivered", DeliveryStatus.delivered),
])
def test_forward_statuses_are_applied(app, fx, client, database, events, twilio_status, expected):
    msg_id = _outbound(database, fx)
    res = _post(client, {"MessageStatus": twilio_status})
    assert res.status_code == 204
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == expected
    assert [e.payload["deliveryStatus"] for e in events
            if e.type == "message.status_changed"] == [twilio_status]


@pytest.mark.parametrize("twilio_status,expected", [
    ("undelivered", DeliveryStatus.undelivered),
    ("failed", DeliveryStatus.failed),
])
def test_failure_statuses_carry_twilio_error_details(app, fx, client, database,
                                                     twilio_status, expected):
    msg_id = _outbound(database, fx)
    res = _post(client, {"MessageStatus": twilio_status, "ErrorCode": "30007",
                         "ErrorMessage": "Carrier violation"})
    assert res.status_code == 204
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.delivery_status == expected
        assert m.provider_error_code == "30007"
        assert m.provider_error_message == "Carrier violation"


@pytest.mark.parametrize("twilio_status", ["queued", "accepted", "sending", "scheduled", "read"])
def test_intermediate_statuses_are_ignored(app, fx, client, database, events, twilio_status):
    msg_id = _outbound(database, fx)
    assert _post(client, {"MessageStatus": twilio_status}).status_code == 204
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.queued
    assert not any(e.type == "message.status_changed" for e in events)


def test_out_of_order_sent_after_delivered_does_not_regress(app, fx, client, database):
    msg_id = _outbound(database, fx)
    _post(client, {"MessageStatus": "delivered"})
    _post(client, {"MessageStatus": "sent"})
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.delivered


def test_unknown_sid_is_acknowledged(app, fx, client):
    """Twilio does not retry status callbacks, and a 4xx only makes it log an alarm; a SID we
    do not hold (a retry reset it, or a message sent outside the app) is simply not ours."""
    res = client.post("/api/hooks/sms/status",
                      data={"MessageSid": "SMunknown", "MessageStatus": "delivered"},
                      headers={"X-Mock-Secret": "dev"})
    assert res.status_code == 204


def test_bad_signature_is_rejected(app, fx, client, database):
    msg_id = _outbound(database, fx)
    assert _post(client, {"MessageStatus": "delivered"}, secret="wrong").status_code == 401
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.queued
