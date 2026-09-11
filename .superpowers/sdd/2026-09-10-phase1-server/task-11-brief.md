### Task 11: Conversations domain, the send path, the inbound path, and the SMS webhook (§11.1 #1, #2, #5)

**Files:**
- Create: `server/app/domain/conversations.py`, `server/app/channels/inbound.py`, `server/app/api/hooks.py`, `server/tests/test_inbound.py`, `server/tests/test_send.py`
- Modify: `server/app/domain/messages.py` (add `send`, `record_inbound`), `server/app/schemas/conversations.py` (add conversation shapes), `server/app/__init__.py`, `server/tests/factories.py` (add `inbound(client, fx, from_phone, body, to=None)` helper)

**Interfaces:**
- Produces: `conversations.find_or_create_for_guest(db, property_id, guest, stay=None) -> tuple[Conversation, bool]` (reopens archived); `conversations.get(db, property_id, conversation_id) -> Conversation` (404); `conversations.sla_minutes(db, property_id) -> int`; `conversations.auto_resolve_hours(db, property_id) -> int`; `messages.send(db, property_id, conversation_id, body, *, author_user_id, author_type=AuthorType.staff, digital_asset_id=None, draft_prompt_id=None, allow_opt_out_confirmation=False, ip=None, user_agent=None) -> Message`; `messages.record_inbound(db, property_id, conversation, body, provider_message_id, *, redacted) -> Message`; `inbound.handle(db, property_id, msg: InboundMessage) -> InboundResult(conversation, message, created_conversation, keyword)`; `POST /api/hooks/sms/inbound` (form-encoded Twilio fields, `X-Mock-Secret`); `ConversationSummary`, `GuestOut`, `StayOut` schemas. Test helper `inbound(client, fx, from_phone, body, to=None) -> Response`.

- [ ] **Step 1: Write the failing tests**

Add to `server/tests/factories.py`:
```python
def inbound(client, fx, from_phone: str, body: str, to: str | None = None, sid: str | None = None):
    import uuid

    return client.post(
        "/api/hooks/sms/inbound",
        data={"From": from_phone, "To": to or fx.property_a.sms_number, "Body": body,
              "MessageSid": sid or f"SM{uuid.uuid4().hex[:10]}"},
        headers={"X-Mock-Secret": "dev"},
    )
```

`server/tests/test_inbound.py`:
```python
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
```

`server/tests/test_send.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_inbound.py tests/test_send.py -q`
Expected: FAIL — 404 on the webhook, `ImportError` for `messages.send`.

- [ ] **Step 3: Add conversation shapes to `app/schemas/conversations.py`**

Append:
```python
from datetime import date

from app.schemas.enums import ConversationStatus, SmsConsentStatus, StayStatus


class GuestOut(CamelModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    phone_e164: str
    email: str | None = None
    loyalty_tier: str | None = None
    vip: bool
    sms_consent_status: SmsConsentStatus
    notes_summary: str | None = None


class StayOut(CamelModel):
    id: str
    room_number: str | None = None
    room_type: str | None = None
    status: StayStatus
    arrival_date: date
    departure_date: date
    adults: int
    children: int
    is_return_guest: bool
    stay_count: int


class ConversationSummary(CamelModel):
    id: str
    status: ConversationStatus
    guest: GuestOut
    room_number: str | None = None
    assigned_user_id: str | None = None
    assigned_department_id: str | None = None
    channel_primary: Channel
    last_guest_message_at: datetime | None = None
    last_staff_message_at: datetime | None = None
    last_message_preview: str | None = None
    sla_due_at: datetime | None = None
    unanswered: bool
    open_work_order_count: int
    snoozed_until: datetime | None = None
```

(Keep the existing `MessageOut`; `ConversationDetail`, `NoteOut`, etc. arrive in Task 12.)

- [ ] **Step 4: Write `app/domain/conversations.py` (creation half; list/detail/assign arrive in Task 12)**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import NotFound
from app.models import Conversation, Guest, Property, Stay
from app.realtime.broadcast import queue_event
from app.schemas.enums import Channel, ConversationStatus


def get(db: Session, property_id: str, conversation_id: str) -> Conversation:
    c = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                             Conversation.property_id == property_id))
    if c is None:
        raise NotFound("Conversation not found")
    return c


def _setting(db: Session, property_id: str, key: str, default: int) -> int:
    settings = db.scalar(select(Property.settings).where(Property.id == property_id)) or {}
    return int(settings.get(key, default))


def sla_minutes(db: Session, property_id: str) -> int:
    return _setting(db, property_id, "sla_minutes", 15)


def auto_resolve_hours(db: Session, property_id: str) -> int:
    return _setting(db, property_id, "auto_resolve_hours", 4)


def find_or_create_for_guest(db: Session, property_id: str, guest: Guest,
                             stay: Stay | None = None) -> tuple[Conversation, bool]:
    """Returns the guest's single live conversation, reopening an archived one if that is all there is."""
    c = db.scalar(
        select(Conversation).where(Conversation.property_id == property_id,
                                   Conversation.guest_id == guest.id)
        .order_by(Conversation.updated_at.desc())
    )
    if c is None:
        c = Conversation(property_id=property_id, guest_id=guest.id, stay_id=stay.id if stay else None,
                         status=ConversationStatus.open, channel_primary=Channel.sms)
        db.add(c)
        db.flush()
        return c, True
    if c.status == ConversationStatus.archived:
        c.status = ConversationStatus.open
        c.archived_at = None
        c.resolution_category_id = None
    elif c.status == ConversationStatus.snoozed:
        c.status = ConversationStatus.open
        c.snoozed_until = None
    if stay and c.stay_id != stay.id:
        c.stay_id = stay.id
    db.flush()
    return c, False


def touch_updated(db: Session, c: Conversation) -> None:
    c.updated_at = clock.now()
    queue_event(db, c.property_id, "conversation.updated", {"id": c.id})
```

- [ ] **Step 5: Add `send` and `record_inbound` to `app/domain/messages.py`**

Add these imports at the top of `messages.py`:
```python
from datetime import timedelta

from app.domain import audit, consent
from app.domain import conversations as conv_domain
from app.domain.redaction import redact
from app.errors import ValidationFailed
from app.models import Conversation, DigitalAsset, Guest, WorkOrder
from app.schemas.enums import AuthorType, Channel, DraftPromptStatus
```
(`DraftPrompt`/`WorkOrder` are used by the `draft_prompt_id` branch; the model already exists.)

Then append:
```python
MAX_BODY = 1600


def send(db: Session, property_id: str, conversation_id: str, body: str, *,
         author_user_id: str | None, author_type: AuthorType = AuthorType.staff,
         digital_asset_id: str | None = None, draft_prompt_id: str | None = None,
         allow_opt_out_confirmation: bool = False, ip: str | None = None,
         user_agent: str | None = None) -> Message:
    """THE outbound path. Every message to a guest goes through here (design.md §9.1)."""
    body = (body or "").strip()
    if not body:
        raise ValidationFailed("Message body is empty")
    if len(body) > MAX_BODY:
        raise ValidationFailed(f"Message body exceeds {MAX_BODY} characters")

    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    if guest.sms_consent_status == SmsConsentStatus.opted_out and not allow_opt_out_confirmation:
        # The caller's session will roll back when ConsentError propagates, so the audit row gets its own
        # session. Nothing has been written in `db` yet at this point, so SQLite WAL allows the second writer.
        with get_db().session() as audit_db:
            audit.record(audit_db, property_id, author_user_id, "message.rejected_opted_out", "conversation",
                         conv.id, after={"body_length": len(body)}, ip=ip, user_agent=user_agent)
    consent.assert_can_send(guest, allow_opt_out_confirmation=allow_opt_out_confirmation)

    if digital_asset_id:
        asset = db.scalar(select(DigitalAsset).where(DigitalAsset.id == digital_asset_id,
                                                     DigitalAsset.property_id == property_id))
        if asset is None:
            raise ValidationFailed("Unknown digital asset")
        body = f"{body} /a/{asset.short_code}"
        asset.send_count += 1

    now = clock.now()
    m = Message(conversation_id=conv.id, property_id=property_id, direction=Direction.outbound,
                author_type=author_type, author_user_id=author_user_id, channel=Channel.sms,
                body=body, digital_asset_id=digital_asset_id, delivery_status=DeliveryStatus.queued,
                sent_at=now)
    db.add(m)

    conv.last_staff_message_at = now
    conv.sla_due_at = None
    conv.sla_breach_notified_at = None
    if conv.first_response_seconds is None and conv.last_guest_message_at is not None \
            and author_type == AuthorType.staff:
        conv.first_response_seconds = int((now - conv.last_guest_message_at).total_seconds())

    if draft_prompt_id:
        from app.models import DraftPrompt

        dp = db.scalar(select(DraftPrompt).where(DraftPrompt.id == draft_prompt_id,
                                                 DraftPrompt.property_id == property_id,
                                                 DraftPrompt.conversation_id == conv.id))
        if dp is not None and dp.status == DraftPromptStatus.pending:
            dp.status = DraftPromptStatus.sent
            dp.resolved_at = now
            dp.resolved_by_user_id = author_user_id
            wo = db.get(WorkOrder, dp.work_order_id)
            if wo is not None:
                wo.guest_notified_at = now

    db.flush()
    jobs.enqueue(db, "outbound.send", {"message_id": m.id})
    audit.record(db, property_id, author_user_id, "message.sent", "message", m.id,
                 after={"conversation_id": conv.id, "length": len(body)}, ip=ip, user_agent=user_agent)
    queue_event(db, property_id, "message.created",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    conv_domain.touch_updated(db, conv)
    return m


def record_inbound(db: Session, property_id: str, conv: Conversation, body: str,
                   provider_message_id: str, *, start_sla: bool = True) -> Message:
    clean, redacted = redact(body)
    now = clock.now()
    m = Message(conversation_id=conv.id, property_id=property_id, direction=Direction.inbound,
                author_type=AuthorType.guest, channel=Channel.sms, body=clean, redacted=redacted,
                delivery_status=DeliveryStatus.delivered, provider_message_id=provider_message_id,
                sent_at=now, delivered_at=now)
    db.add(m)
    conv.last_guest_message_at = now
    if start_sla:
        conv.sla_due_at = now + timedelta(minutes=conv_domain.sla_minutes(db, property_id))
        conv.sla_breach_notified_at = None
    db.flush()
    queue_event(db, property_id, "message.created",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m
```

Add `from app.db import get_db` and `SmsConsentStatus` to the imports for the consent block above.

- [ ] **Step 6: Write `app/channels/inbound.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.domain import consent, guests, messages, notifications, stays
from app.domain import conversations as conv_domain
from app.models import Conversation, Message, Property
from app.realtime.broadcast import queue_event
from app.schemas.enums import AuthorType, SmsConsentStatus


@dataclass
class InboundResult:
    conversation: Conversation
    message: Message
    created_conversation: bool
    keyword: str | None


def property_for_number(db: Session, to_number: str) -> Property | None:
    return db.scalar(select(Property).where(Property.sms_number == guests.normalize_phone(to_number)))


def handle(db: Session, property_id: str, msg: InboundMessage) -> InboundResult:
    existing = db.scalar(select(Message).where(Message.property_id == property_id,
                                               Message.provider_message_id == msg.provider_message_id))
    if existing is not None:
        conv = db.get(Conversation, existing.conversation_id)
        return InboundResult(conv, existing, False, None)

    guest, _ = guests.find_or_create_by_phone(db, property_id, msg.from_)
    if guest.sms_consent_status == SmsConsentStatus.unknown:
        consent.opt_in(db, guest, "inbound_sms")

    stay = stays.find_in_house_for_guest(db, property_id, guest.id)
    conv, created = conv_domain.find_or_create_for_guest(db, property_id, guest, stay)

    keyword = consent.classify_keyword(msg.body)
    message = messages.record_inbound(db, property_id, conv, msg.body, msg.provider_message_id,
                                      start_sla=keyword is None)

    prop = db.get(Property, property_id)
    if keyword == "stop":
        consent.opt_out(db, guest, "sms_keyword")
        messages.send(db, property_id, conv.id, consent.STOP_CONFIRMATION(prop.name),
                      author_user_id=None, author_type=AuthorType.system,
                      allow_opt_out_confirmation=True)
    elif keyword == "start":
        consent.opt_in(db, guest, "sms_keyword")
        messages.send(db, property_id, conv.id, f"You're resubscribed to {prop.name} messages.",
                      author_user_id=None, author_type=AuthorType.system)
    elif keyword == "help":
        help_text = (prop.settings or {}).get("help_text") or f"{prop.name}: reply to this number."
        messages.send(db, property_id, conv.id, help_text, author_user_id=None,
                      author_type=AuthorType.system, allow_opt_out_confirmation=True)
    else:
        name = f"{guest.first_name or ''} {guest.last_name or ''}".strip() or guest.phone_e164
        room = f" · {stay.room_number}" if stay and stay.room_number else ""
        notifications.notify_user_or_department(
            db, property_id, user_id=conv.assigned_user_id, department_id=conv.assigned_department_id,
            type="message.inbound", title=f"{name}{room}", body=message.body[:140],
            entity_type="conversation", entity_id=conv.id)

    queue_event(db, property_id, "conversation.created" if created else "conversation.updated",
                {"id": conv.id})
    return InboundResult(conv, message, created, keyword)
```

Because `messages.send` calls `conv_domain.touch_updated`, a keyword reply will also emit `conversation.updated`; the test only checks `conversation.*` events for the first-message case (which emits exactly one `conversation.created`), so `handle` must **not** call `touch_updated` itself — it queues its own single event as written above. Ensure `messages.send` is not invoked in the non-keyword branch.

- [ ] **Step 7: Write the webhook blueprint and register it**

`server/app/api/hooks.py`:
```python
from flask import Blueprint, request

from app.api._util import db_session, no_content
from app.channels import inbound
from app.channels.registry import get_sms_adapter
from app.errors import NotFound, Unauthorized
from app.ratelimit import rate_limited, webhook_limiter

bp = Blueprint("hooks", __name__, url_prefix="/api/hooks")


@bp.post("/sms/inbound")
@rate_limited(webhook_limiter)
def sms_inbound():
    adapter = get_sms_adapter()
    if not adapter.verify_inbound(request):
        raise Unauthorized("Bad webhook signature")
    payload = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    msg = adapter.parse_inbound(payload)
    with db_session() as db:
        prop = inbound.property_for_number(db, msg.to)
        if prop is None:
            raise NotFound("No property uses that number")
        inbound.handle(db, prop.id, msg)
    return no_content()
```

Register `hooks.bp` in `create_app`. Also register a minimal conversations blueprint now so `test_stop_opts_out…` and `test_send_via_api…` can POST a message; the full blueprint is Task 12. Create `server/app/api/conversations.py` with just:

```python
from flask import Blueprint, g

from app.api._util import client_meta, db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import messages
from app.schemas.conversations import MessageOut, SendMessageRequest

bp = Blueprint("conversations", __name__, url_prefix="/api/p/<property_id>/conversations")


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
@require_capability("reply")
def send_message(property_id: str, conversation_id: str):
    body = parse_body(SendMessageRequest)
    ip, ua = client_meta()
    with db_session() as db:
        m = messages.send(db, g.property_id, conversation_id, body.body, author_user_id=g.user.id,
                          digital_asset_id=body.digital_asset_id, draft_prompt_id=body.draft_prompt_id,
                          ip=ip, user_agent=ua)
        return ok(MessageOut.model_validate(m), 201)
```

and add to `app/schemas/conversations.py`:
```python
from pydantic import Field


class SendMessageRequest(CamelModel):
    body: str = Field(min_length=1, max_length=1600)
    digital_asset_id: str | None = None
    draft_prompt_id: str | None = None
```

- [ ] **Step 8: Run the tests**

Run: `python -m pytest -q`
Expected: all pass. The isolation suite now covers `POST …/conversations/<id>/messages` — it must return 403 for the cross-property user *before* the 404 for the dummy conversation id, which the decorator order guarantees.

- [ ] **Step 9: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): conversations, the consent-enforced send path, inbound SMS handling and webhook"
```

---

