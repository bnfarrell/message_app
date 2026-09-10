from app.channels.mock_sms import MockSmsAdapter
from app.models import Message
from app.queue import jobs
from app.schemas.enums import DeliveryStatus, Direction
from tests.factories import make_conversation, make_message


def _outbound(database, fx, to_phone: str):
    from app.models import Guest

    with database.session() as db:
        guest = db.get(Guest, fx.guest_inhouse_a.id)  # re-attach: fixture objects are detached
        guest.phone_e164 = to_phone
        conv = make_conversation(db, fx, guest)
        msg = make_message(db, conv, direction=Direction.outbound, body="Hello")
        jobs.enqueue(db, "outbound.send", {"message_id": msg.id})
    return msg.id


def test_send_delivers_in_two_steps_and_broadcasts(app, fx, database, worker, events):
    msg_id = _outbound(database, fx, "+15551234567")
    worker.tick()  # outbound.send → provider id, schedules mock.delivery_status jobs
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.provider_message_id.startswith("mock-")
        assert m.delivery_status == DeliveryStatus.queued
    from app import clock

    clock.advance(seconds=0.5)
    worker.tick()
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.sent
    clock.advance(seconds=1)
    worker.tick()
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.delivery_status == DeliveryStatus.delivered
        assert m.delivered_at is not None
    statuses = [e.payload["deliveryStatus"] for e in events if e.type == "message.status_changed"]
    assert statuses == ["sent", "delivered"]


def test_numbers_ending_0000_fail_with_carrier_code(app, fx, database, worker, events):
    msg_id = _outbound(database, fx, "+15552000000")
    worker.tick()
    from app import clock

    clock.advance(seconds=0.5)
    worker.tick()
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.delivery_status == DeliveryStatus.failed
        assert m.provider_error_code == "30007"
        assert "mock" in m.provider_error_message.lower()


def test_retry_requeues_a_failed_message(app, fx, database, worker):
    from app import clock
    from app.domain import messages

    msg_id = _outbound(database, fx, "+15552000000")
    worker.tick()
    clock.advance(seconds=0.5)
    worker.tick()
    with database.session() as db:
        from app.models import Guest

        db.get(Guest, fx.guest_inhouse_a.id).phone_e164 = "+15551234567"  # a working number for the retry
        m = messages.retry(db, fx.property_a.id, msg_id)
        assert m.delivery_status == DeliveryStatus.queued
        assert m.provider_error_code is None
    worker.tick()
    clock.advance(seconds=2)
    worker.tick()
    worker.tick()
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.delivered


def test_provider_exception_marks_failed_without_retry(app, fx, database, worker, events, monkeypatch):
    def _raise(self, db, to, body, *, message_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(MockSmsAdapter, "send", _raise)
    msg_id = _outbound(database, fx, "+15551234567")
    ran = worker.tick()
    assert ran == 1
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.delivery_status == DeliveryStatus.failed
        assert m.provider_error_code == "ADAPTER_ERROR"
        assert "boom" in m.provider_error_message
    statuses = [e.payload["deliveryStatus"] for e in events if e.type == "message.status_changed"]
    assert statuses == ["failed"]


def test_update_delivery_status_ignores_backward_transition(app, fx, database, events):
    from app.domain import messages

    msg_id = _outbound(database, fx, "+15551234567")
    with database.session() as db:
        messages.update_delivery_status(db, fx.property_a.id, msg_id, DeliveryStatus.delivered)
    events.clear()
    with database.session() as db:
        m = messages.update_delivery_status(db, fx.property_a.id, msg_id, DeliveryStatus.sent)
        assert m.delivery_status == DeliveryStatus.delivered
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.delivered
    assert not any(e.type == "message.status_changed" for e in events)


def test_parse_inbound_reads_twilio_field_names(app):
    a = MockSmsAdapter(secret="dev")
    m = a.parse_inbound({"From": "+15551234567", "To": "+15550100", "Body": " hi ", "MessageSid": "SM1"})
    assert (m.from_, m.to, m.body, m.provider_message_id) == ("+15551234567", "+15550100", "hi", "SM1")


def test_verify_inbound_checks_shared_secret(app):
    a = MockSmsAdapter(secret="dev")
    with app.test_request_context(headers={"X-Mock-Secret": "dev"}):
        from flask import request

        assert a.verify_inbound(request) is True
    with app.test_request_context(headers={"X-Mock-Secret": "wrong"}):
        from flask import request

        assert a.verify_inbound(request) is False
