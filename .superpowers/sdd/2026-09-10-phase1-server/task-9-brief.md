### Task 9: Channel adapter interface, MockSmsAdapter, outbound send and delivery-status handlers

**Files:**
- Create: `server/app/channels/__init__.py`, `server/app/channels/base.py`, `server/app/channels/mock_sms.py`, `server/app/channels/registry.py`, `server/app/queue/handlers/outbound.py`, `server/app/queue/handlers/mock_delivery.py`, `server/app/domain/messages.py` (delivery-status half; `send`/`record_inbound` arrive in Task 11), `server/app/schemas/conversations.py` (message shapes only for now), `server/tests/factories.py`, `server/tests/test_mock_sms.py`

**Interfaces:**
- Produces: `ChannelAdapter` Protocol (`channel`, `supports_rich_media`, `max_length`, `send(db, to, body, *, message_id) -> SendResult`, `verify_inbound(request) -> bool`, `parse_inbound(payload) -> InboundMessage`); dataclasses `SendResult(provider_message_id)`, `InboundMessage(from_, to, body, provider_message_id)`; `MockSmsAdapter`; `registry.get_sms_adapter() -> ChannelAdapter` (from `current_app.extensions["sms_adapter"]`); handlers `outbound.send` and `mock.delivery_status`; `messages.update_delivery_status(db, property_id, message_id, status, *, provider_message_id=None, error_code=None, error_message=None) -> Message`; `messages.retry(db, property_id, message_id) -> Message`; `MessageOut` schema; test factories `make_conversation(db, fx, guest=None, **overrides) -> Conversation`, `make_message(db, conversation, *, direction, body, **overrides) -> Message`.

- [ ] **Step 1: Write the failing tests**

`server/tests/factories.py`:
```python
from __future__ import annotations

from sqlalchemy.orm import Session

from app import clock
from app.models import Conversation, Guest, Message
from app.schemas.enums import AuthorType, Channel, ConversationStatus, DeliveryStatus, Direction


def make_conversation(db: Session, fx, guest: Guest | None = None, **overrides) -> Conversation:
    guest = guest or fx.guest_inhouse_a
    stay_id = fx.stay_inhouse_a.id if guest.id == fx.guest_inhouse_a.id else None
    c = Conversation(property_id=guest.property_id, guest_id=guest.id, stay_id=stay_id,
                     status=ConversationStatus.open, channel_primary=Channel.sms)
    for k, v in overrides.items():
        setattr(c, k, v)
    db.add(c)
    db.flush()
    return c


def make_message(db: Session, conversation: Conversation, *, direction: Direction, body: str,
                 **overrides) -> Message:
    m = Message(
        conversation_id=conversation.id, property_id=conversation.property_id, direction=direction,
        author_type=AuthorType.guest if direction == Direction.inbound else AuthorType.staff,
        channel=Channel.sms, body=body,
        delivery_status=DeliveryStatus.delivered if direction == Direction.inbound else DeliveryStatus.queued,
        sent_at=clock.now(),
    )
    for k, v in overrides.items():
        setattr(m, k, v)
    db.add(m)
    db.flush()
    return m
```

`server/tests/test_mock_sms.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_mock_sms.py -q`
Expected: FAIL with `ModuleNotFoundError: app.channels`.

- [ ] **Step 3: Write the adapter interface and the mock**

`server/app/channels/__init__.py` — empty.

`server/app/channels/base.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from flask import Request
from sqlalchemy.orm import Session

from app.schemas.enums import Channel


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str


@dataclass(frozen=True)
class InboundMessage:
    from_: str
    to: str
    body: str
    provider_message_id: str


class ChannelAdapter(Protocol):
    channel: Channel
    supports_rich_media: bool
    max_length: int

    def send(self, db: Session, to: str, body: str, *, message_id: str) -> SendResult: ...

    def verify_inbound(self, request: Request) -> bool: ...

    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage: ...
```

`server/app/channels/mock_sms.py`:
```python
"""Fake SMS wire. Everything above it — consent, queueing, delivery status, retry — is real."""
from __future__ import annotations

import hmac
import uuid
from datetime import timedelta
from typing import Mapping

from flask import Request
from sqlalchemy.orm import Session

from app import clock
from app.channels.base import InboundMessage, SendResult
from app.queue import jobs
from app.schemas.enums import Channel

FAIL_SUFFIX = "0000"
FAIL_CODE = "30007"
FAIL_MESSAGE = "Carrier violation (mock)"


class MockSmsAdapter:
    channel = Channel.sms
    supports_rich_media = False
    max_length = 1600

    def __init__(self, secret: str = "dev"):
        self.secret = secret

    def send(self, db: Session, to: str, body: str, *, message_id: str) -> SendResult:
        provider_id = f"mock-{uuid.uuid4().hex[:12]}"
        now = clock.now()
        if to.endswith(FAIL_SUFFIX):
            jobs.enqueue(db, "mock.delivery_status",
                         {"message_id": message_id, "status": "failed",
                          "error_code": FAIL_CODE, "error_message": FAIL_MESSAGE},
                         run_at=now + timedelta(milliseconds=400), max_attempts=1)
        else:
            jobs.enqueue(db, "mock.delivery_status", {"message_id": message_id, "status": "sent"},
                         run_at=now + timedelta(milliseconds=400), max_attempts=1)
            jobs.enqueue(db, "mock.delivery_status", {"message_id": message_id, "status": "delivered"},
                         run_at=now + timedelta(milliseconds=1200), max_attempts=1)
        return SendResult(provider_message_id=provider_id)

    def verify_inbound(self, request: Request) -> bool:
        given = request.headers.get("X-Mock-Secret", "")
        return hmac.compare_digest(given, self.secret)

    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage:
        return InboundMessage(
            from_=payload.get("From", "").strip(),
            to=payload.get("To", "").strip(),
            body=(payload.get("Body") or "").strip(),
            provider_message_id=payload.get("MessageSid") or f"mock-in-{uuid.uuid4().hex[:12]}",
        )
```

`server/app/channels/registry.py`:
```python
from flask import Flask, current_app

from app.channels.base import ChannelAdapter
from app.channels.mock_sms import MockSmsAdapter
from app.config import Config


def build_sms_adapter(config: Config) -> ChannelAdapter:
    if config.SMS_ADAPTER == "mock":
        return MockSmsAdapter(secret=config.MOCK_SMS_SECRET)
    raise ValueError(f"Unknown SMS_ADAPTER {config.SMS_ADAPTER!r}; Phase 1 supports 'mock'")


def install(app: Flask, config: Config) -> None:
    app.extensions["sms_adapter"] = build_sms_adapter(config)


def get_sms_adapter() -> ChannelAdapter:
    return current_app.extensions["sms_adapter"]
```

In `create_app`, right after the database is registered: `from app.channels import registry as channel_registry; channel_registry.install(app, config)`.

- [ ] **Step 4: Write the message schema and the delivery-status half of the messages domain**

`server/app/schemas/conversations.py` (Task 11 adds the conversation shapes to this same file):
```python
from datetime import datetime

from app.schemas.common import CamelModel
from app.schemas.enums import AuthorType, Channel, DeliveryStatus, Direction


class MessageOut(CamelModel):
    id: str
    conversation_id: str
    direction: Direction
    author_type: AuthorType
    author_user_id: str | None = None
    channel: Channel
    body: str
    digital_asset_id: str | None = None
    delivery_status: DeliveryStatus
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    redacted: bool
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
```

`server/app/domain/messages.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflict, NotFound
from app.models import Message
from app.queue import jobs
from app.realtime.broadcast import queue_event
from app.schemas.conversations import MessageOut
from app.schemas.enums import DeliveryStatus, Direction


def _get(db: Session, property_id: str, message_id: str) -> Message:
    m = db.scalar(select(Message).where(Message.id == message_id, Message.property_id == property_id))
    if m is None:
        raise NotFound("Message not found")
    return m


def update_delivery_status(db: Session, property_id: str, message_id: str, status: DeliveryStatus, *,
                           provider_message_id: str | None = None, error_code: str | None = None,
                           error_message: str | None = None) -> Message:
    m = _get(db, property_id, message_id)
    m.delivery_status = status
    if provider_message_id:
        m.provider_message_id = provider_message_id
    if status == DeliveryStatus.delivered:
        m.delivered_at = clock.now()
    if status in (DeliveryStatus.failed, DeliveryStatus.undelivered):
        m.provider_error_code = error_code
        m.provider_error_message = error_message
    db.flush()
    queue_event(db, property_id, "message.status_changed",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m


def retry(db: Session, property_id: str, message_id: str) -> Message:
    m = _get(db, property_id, message_id)
    if m.direction != Direction.outbound or m.delivery_status not in (
        DeliveryStatus.failed, DeliveryStatus.undelivered
    ):
        raise Conflict("Only failed outbound messages can be retried")
    m.delivery_status = DeliveryStatus.queued
    m.provider_error_code = None
    m.provider_error_message = None
    m.provider_message_id = None
    db.flush()
    jobs.enqueue(db, "outbound.send", {"message_id": m.id})
    queue_event(db, property_id, "message.status_changed",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m
```

- [ ] **Step 5: Write the two handlers**

`server/app/queue/handlers/outbound.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.registry import get_sms_adapter
from app.domain import messages
from app.models import Conversation, Guest, Message
from app.queue.handlers import handler
from app.schemas.enums import DeliveryStatus


@handler("outbound.send")
def outbound_send(db: Session, payload: dict) -> None:
    msg = db.get(Message, payload["message_id"])
    if msg is None or msg.delivery_status != DeliveryStatus.queued:
        return  # already handled or retried; idempotent
    conv = db.get(Conversation, msg.conversation_id)
    guest = db.get(Guest, conv.guest_id)
    adapter = get_sms_adapter()
    try:
        result = adapter.send(db, guest.phone_e164, msg.body, message_id=msg.id)
    except Exception as exc:  # provider threw: mark failed, then re-raise so the job retries
        messages.update_delivery_status(db, msg.property_id, msg.id, DeliveryStatus.failed,
                                        error_code="ADAPTER_ERROR", error_message=repr(exc)[:500])
        raise
    msg.provider_message_id = result.provider_message_id
    db.flush()
```

`server/app/queue/handlers/mock_delivery.py`:
```python
from sqlalchemy.orm import Session

from app.domain import messages
from app.models import Message
from app.queue.handlers import handler
from app.schemas.enums import DeliveryStatus


@handler("mock.delivery_status")
def mock_delivery_status(db: Session, payload: dict) -> None:
    msg = db.get(Message, payload["message_id"])
    if msg is None:
        return
    target = DeliveryStatus(payload["status"])
    # A retry resets the message to queued and schedules a new sequence; stale events must not
    # overwrite it. Only advance forward: queued→sent→delivered, or queued/sent→failed.
    order = [DeliveryStatus.queued, DeliveryStatus.sent, DeliveryStatus.delivered]
    if target in order and msg.delivery_status in order and order.index(target) <= order.index(msg.delivery_status):
        return
    if msg.provider_message_id is None:
        return  # message was reset by a retry after this job was scheduled
    messages.update_delivery_status(db, msg.property_id, msg.id, target,
                                    error_code=payload.get("error_code"),
                                    error_message=payload.get("error_message"))
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): ChannelAdapter interface, MockSmsAdapter, outbound send and delivery-status jobs"
```

---

