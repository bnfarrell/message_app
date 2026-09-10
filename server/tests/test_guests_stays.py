from app.domain import guests, stays
from app.schemas.enums import SmsConsentStatus


def test_normalize_phone():
    assert guests.normalize_phone("(555) 123-4567") == "+15551234567"
    assert guests.normalize_phone("15551234567") == "+15551234567"
    assert guests.normalize_phone("+44 20 7946 0958") == "+442079460958"


def test_find_or_create_by_phone_is_idempotent_and_property_scoped(app, fx, database):
    with database.session() as db:
        g1, created1 = guests.find_or_create_by_phone(db, fx.property_a.id, "+15550001111")
        g2, created2 = guests.find_or_create_by_phone(db, fx.property_a.id, "+1 (555) 000-1111")
        gb, createdb = guests.find_or_create_by_phone(db, fx.property_b.id, "+15550001111")
    assert created1 and not created2 and createdb
    assert g1.id == g2.id and gb.id != g1.id
    assert g1.sms_consent_status == SmsConsentStatus.unknown


def test_find_in_house_by_phone_matches_checked_in_stay_only(app, fx, database):
    with database.session() as db:
        hit = stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_inhouse_a.phone_e164)
        assert hit is not None and hit[1].room_number == "412"
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_nostay_a.phone_e164) is None
        # Same phone at another property is not in-house here.
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_b.phone_e164) is None
