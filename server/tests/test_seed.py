import pytest
from sqlalchemy import func, select

from app.db import Database
from app.models import (Conversation, DigitalAsset, DraftPrompt, Guest, Message, Property, PropertyMembership,
                        QuickReply, ResolutionCategory, Stay, UserAccount, WorkOrder)
from app.schemas.enums import ConversationStatus, DeliveryStatus, SmsConsentStatus, StayStatus, WorkOrderStatus
from seed.seed import run


def test_seed_matches_spec_counts(tmp_path):
    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    summary = run(url, reset=True)
    db_ = Database(url)
    with db_.session() as db:
        count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where))  # noqa: E731
        hvh = db.scalar(select(Property).where(Property.code == "HVH"))
        lsi = db.scalar(select(Property).where(Property.code == "LSI"))
        assert hvh and lsi
        assert count(PropertyMembership, PropertyMembership.property_id == hvh.id) == 12
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.checked_in) == 85
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.reserved) == 10
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.checked_out) == 8
        assert count(Conversation, Conversation.property_id == hvh.id) == 30
        assert count(Conversation, Conversation.property_id == hvh.id, Conversation.status == ConversationStatus.archived) == 5
        assert count(DraftPrompt) == 2
        assert count(Guest, Guest.sms_consent_status == SmsConsentStatus.opted_out) == 1
        assert count(Message, Message.redacted.is_(True)) == 1
        assert count(WorkOrder, WorkOrder.property_id == hvh.id,
                     WorkOrder.status.in_([WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress,
                                           WorkOrderStatus.blocked, WorkOrderStatus.complete])) == 15
        assert count(WorkOrder, WorkOrder.source_conversation_id.isnot(None)) >= 6
        assert count(QuickReply, QuickReply.property_id == hvh.id) >= 15
        assert count(DigitalAsset, DigitalAsset.property_id == hvh.id) == 8
        assert count(ResolutionCategory, ResolutionCategory.property_id == hvh.id) >= 10
        assert count(Message, Message.delivery_status == DeliveryStatus.failed) >= 1
        assert db.scalar(select(UserAccount).where(UserAccount.email == "ava@hvh.test")) is not None
        # SeedSummary must match real rows, not an in-memory counter that a rewire can desync
        # (the showcase conversation's messages are deleted and re-added after being counted).
        assert summary.properties == count(Property)
        assert summary.users == count(UserAccount)
        assert summary.guests == count(Guest)
        assert summary.stays == count(Stay)
        assert summary.conversations == count(Conversation)
        assert summary.messages == count(Message)
        assert summary.work_orders == count(WorkOrder)
    db_.engine.dispose()
    assert summary.conversations == 30

    # Deterministic: running again yields identical guest phone numbers.
    url2 = f"sqlite:///{(tmp_path / 'seed2.db').as_posix()}"
    run(url2, reset=True)
    a, b = Database(url), Database(url2)
    with a.session() as da, b.session() as dbb:
        pa = sorted(da.scalars(select(Guest.phone_e164)).all())
        pb = sorted(dbb.scalars(select(Guest.phone_e164)).all())
    assert pa == pb
    a.engine.dispose(); b.engine.dispose()


def test_seeded_users_can_log_in(tmp_path):
    from app import create_app
    from app.config import Config

    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    run(url, reset=True)
    app = create_app(Config(DATABASE_URL=url, TESTING=True))
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": "ava@hvh.test", "password": "Password123!"}).status_code == 200
    body = c.get("/api/auth/me").get_json()
    assert body["memberships"][0]["role"] == "agent"
    app.extensions["db"].engine.dispose()


def test_reset_refuses_non_sqlite_url():
    with pytest.raises(ValueError, match="sqlite"):
        run("postgresql://x/y", reset=True)


def test_reseeding_same_sqlite_url_is_idempotent(tmp_path):
    # The CLI's everyday-refresh path: `flask seed` run again against the same DATABASE_URL.
    url = f"sqlite:///{(tmp_path / 'reseed.db').as_posix()}"
    first = run(url, reset=True)
    second = run(url, reset=True)
    assert first == second
