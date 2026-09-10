import pytest

from app.domain import guests, stays
from app.errors import ValidationFailed
from app.models import Guest
from app.schemas.enums import SmsConsentStatus


def test_normalize_phone():
    assert guests.normalize_phone("(555) 123-4567") == "+15551234567"
    assert guests.normalize_phone("15551234567") == "+15551234567"
    assert guests.normalize_phone("+44 20 7946 0958") == "+442079460958"


@pytest.mark.parametrize("raw", ["", "   ", "5551234", "123456789012345"])
def test_normalize_phone_rejects_junk(raw):
    with pytest.raises(ValidationFailed):
        guests.normalize_phone(raw)


def test_find_or_create_by_phone_is_idempotent_and_property_scoped(app, fx, database):
    with database.session() as db:
        g1, created1 = guests.find_or_create_by_phone(db, fx.property_a.id, "+15550001111")
        g2, created2 = guests.find_or_create_by_phone(db, fx.property_a.id, "+1 (555) 000-1111")
        gb, createdb = guests.find_or_create_by_phone(db, fx.property_b.id, "+15550001111")
    assert created1 and not created2 and createdb
    assert g1.id == g2.id and gb.id != g1.id
    assert g1.sms_consent_status == SmsConsentStatus.unknown


def test_find_or_create_by_phone_survives_concurrent_insert_race(app, fx, database, monkeypatch):
    # Simulate a second request winning the race between our existence check and our
    # own INSERT: another guest row with the same (property_id, phone) already exists,
    # but we force our own initial find_by_phone lookup to miss (as it would if the
    # winning insert lands in the gap between our SELECT and INSERT), so
    # find_or_create_by_phone must hit the UniqueConstraint, catch it, and return the
    # winner instead of raising IntegrityError.
    phone = "+15550009999"
    with database.session() as db:
        winner = Guest(property_id=fx.property_a.id, phone_e164=phone)
        db.add(winner)
        db.flush()
        winner_id = winner.id

        real_find_by_phone = guests.find_by_phone
        calls = {"n": 0}

        def flaky_find_by_phone(db_, property_id, phone_):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # pretend the row isn't visible yet (the race window)
            return real_find_by_phone(db_, property_id, phone_)

        monkeypatch.setattr(guests, "find_by_phone", flaky_find_by_phone)

        g, created = guests.find_or_create_by_phone(db, fx.property_a.id, phone)

    assert created is False
    assert g.id == winner_id


def test_find_in_house_by_phone_matches_checked_in_stay_only(app, fx, database):
    with database.session() as db:
        hit = stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_inhouse_a.phone_e164)
        assert hit is not None and hit[1].room_number == "412"
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_nostay_a.phone_e164) is None
        # Same phone at another property is not in-house here.
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_b.phone_e164) is None
