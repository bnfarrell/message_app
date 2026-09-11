from collections import defaultdict

import pytest
from sqlalchemy import func, select

from app.db import Database
from app.models import (
    Conversation,
    DigitalAsset,
    DraftPrompt,
    Guest,
    Message,
    Property,
    PropertyMembership,
    QuickReply,
    ResolutionCategory,
    Stay,
    UserAccount,
    WorkOrder,
)
from app.schemas.enums import (
    ConversationStatus,
    DeliveryStatus,
    SmsConsentStatus,
    StayStatus,
    WorkOrderStatus,
)
from seed.seed import run


def test_seed_matches_spec_counts(tmp_path):
    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    summary = run(url, reset=True)
    db_ = Database(url)
    with db_.session() as db:
        count = lambda model, *where: db.scalar(  # noqa: E731
            select(func.count()).select_from(model).where(*where))
        hvh = db.scalar(select(Property).where(Property.code == "HVH"))
        lsi = db.scalar(select(Property).where(Property.code == "LSI"))
        assert hvh and lsi
        assert count(PropertyMembership, PropertyMembership.property_id == hvh.id) == 12
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.checked_in) == 85
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.reserved) == 10
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.checked_out) == 12
        assert count(Conversation, Conversation.property_id == hvh.id) == 31
        assert count(Conversation, Conversation.property_id == hvh.id,
                     Conversation.status == ConversationStatus.archived) == 5
        # Property B is no longer an empty inbox behind the property switcher.
        assert count(Stay, Stay.property_id == lsi.id, Stay.status == StayStatus.checked_in) == 6
        assert count(Conversation, Conversation.property_id == lsi.id) == 4
        assert count(Conversation, Conversation.property_id == lsi.id,
                     Conversation.status == ConversationStatus.archived) == 1
        # spec §8: a guest who texts without being in-house.
        assert count(Conversation, Conversation.stay_id.is_(None)) == 1
        assert count(DraftPrompt) == 2
        assert count(Guest, Guest.sms_consent_status == SmsConsentStatus.opted_out) == 1
        assert count(Message, Message.redacted.is_(True)) == 1
        assert count(WorkOrder, WorkOrder.property_id == hvh.id,
                     WorkOrder.status.in_([WorkOrderStatus.open, WorkOrderStatus.assigned,
                                           WorkOrderStatus.in_progress,
                                           WorkOrderStatus.blocked,
                                           WorkOrderStatus.complete])) == 15
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
    assert summary.conversations == 35
    assert summary.guests == 110 and summary.stays == 113

    # Deterministic: running again yields identical guest phone numbers.
    url2 = f"sqlite:///{(tmp_path / 'seed2.db').as_posix()}"
    run(url2, reset=True)
    a, b = Database(url), Database(url2)
    with a.session() as da, b.session() as dbb:
        pa = sorted(da.scalars(select(Guest.phone_e164)).all())
        pb = sorted(dbb.scalars(select(Guest.phone_e164)).all())
    assert pa == pb
    a.engine.dispose()
    b.engine.dispose()


def test_stay_history_agrees_with_the_denormalised_stay_count(tmp_path):
    """`stay_count` is what the guest panel prints as "4th stay"; the stay list beside it comes
    from the rows. Every guest used to have exactly one row and a random count of up to 6, so the
    panel contradicted itself for 95 of 106 stays and "Previous stays" was empty for everyone."""
    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    run(url, reset=True)
    db_ = Database(url)
    with db_.session() as db:
        rows = db.scalars(select(Stay).order_by(Stay.arrival_date)).all()
        by_guest = defaultdict(list)
        for s in rows:
            by_guest[s.guest_id].append(s)
        for stays in by_guest.values():
            assert [s.stay_count for s in stays] == list(range(1, len(stays) + 1))
            assert [s.is_return_guest for s in stays] == [n > 0 for n in range(len(stays))]
        repeat = {g: s for g, s in by_guest.items() if len(s) > 1}
        assert len(repeat) == 2
        sarah = db.scalar(select(Guest).where(Guest.first_name == "Sarah",
                                              Guest.last_name == "Chen"))
        # Ava's seeded internal note calls Sarah a "Gold member, 4th stay" — so she must have four.
        assert [s.stay_count for s in by_guest[sarah.id]] == [1, 2, 3, 4]
        assert by_guest[sarah.id][-1].status == StayStatus.checked_in
        # A stay that ended a year ago must not claim it checked out yesterday.
        for s in rows:
            if s.actual_checkout_at is not None:
                assert s.actual_checkout_at.date() == s.departure_date
    db_.engine.dispose()


def test_seeded_users_can_log_in(tmp_path):
    from app import create_app
    from app.config import Config

    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    run(url, reset=True)
    app = create_app(Config(DATABASE_URL=url, TESTING=True))
    c = app.test_client()
    res = c.post("/api/auth/login", json={"email": "ava@hvh.test", "password": "Password123!"})
    assert res.status_code == 200
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
