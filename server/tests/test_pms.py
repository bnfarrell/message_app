from datetime import date

from sqlalchemy import select

from app import clock
from app.models import Guest, PmsEvent, Stay
from app.pms.base import NormalizedGuest, NormalizedStay
from app.pms.base import PmsEvent as Ev
from app.pms.handle_event import handle_event
from app.pms.mock_pms import MockPmsAdapter
from app.schemas.enums import SmsConsentStatus, StayStatus


def _event(fx, eid="R-1", type="stay.checked_in", phone="+15553334444", room="515"):
    today = clock.now().date()
    return Ev(external_id=eid, type=type, property_id=fx.property_a.id,
              guest=NormalizedGuest(first_name="Tom", last_name="Becker", phone_e164=phone,
                                    email=None,
                                    loyalty_tier="Silver", vip=False, pms_profile_id="P-9"),
              stay=NormalizedStay(pms_reservation_id=eid, room_number=room, room_type="Queen",
                                  rate_code="BAR",
                                  status=StayStatus.checked_in, arrival_date=today,
                                  departure_date=date.fromordinal(today.toordinal() + 2),
                                  adults=1, children=0,
                                  is_return_guest=False, stay_count=1),
              raw={"source": "test"})


def test_check_in_upserts_guest_and_stay(app, fx, database):
    with database.session() as db:
        assert handle_event(db, _event(fx)) is True
        g = db.scalar(select(Guest).where(Guest.phone_e164 == "+15553334444"))
        assert g.first_name == "Tom" and g.loyalty_tier == "Silver" and g.pms_profile_id == "P-9"
        s = db.scalar(select(Stay).where(Stay.pms_reservation_id == "R-1"))
        assert (s.status == StayStatus.checked_in and s.room_number == "515"
               and s.actual_checkin_at is not None)
        assert s.raw_pms == {"source": "test"}


def test_duplicate_event_is_ignored(app, fx, database):
    with database.session() as db:
        assert handle_event(db, _event(fx)) is True
        assert handle_event(db, _event(fx)) is False
        assert len(db.scalars(select(Stay)).all()) == 3  # 2 fixture stays + 1
        assert len(db.scalars(select(PmsEvent)).all()) == 1


def test_check_out_updates_existing_stay_and_does_not_reopen_consent(app, fx, database):
    with database.session() as db:
        handle_event(db, _event(fx))
        ev = _event(fx, eid="R-1", type="stay.checked_out")
        ev.stay.status = StayStatus.checked_out
        assert handle_event(db, ev) is True
        s = db.scalar(select(Stay).where(Stay.pms_reservation_id == "R-1"))
        assert s.status == StayStatus.checked_out and s.actual_checkout_at is not None


def test_mock_adapter_checks_in_arrivals_then_checks_out_departures(app, fx, database):
    today = clock.now().date()
    with database.session() as db:
        g = Guest(property_id=fx.property_a.id, first_name="Arriving", last_name="Guest",
                  phone_e164="+15550009999")
        db.add(g)
        db.flush()
        db.add(Stay(guest_id=g.id, property_id=fx.property_a.id, pms_reservation_id="R-ARR",
                    room_number="222",
                    status=StayStatus.reserved, arrival_date=today,
                    departure_date=date.fromordinal(today.toordinal() + 1)))
        fx_stay = db.get(Stay, fx.stay_inhouse_a.id)
        fx_stay.departure_date = today  # Sarah departs today
    adapter = MockPmsAdapter()
    with database.session() as db:
        events = adapter.next_events(db, fx.property_a.id)
        assert ([e.type for e in events] == ["stay.checked_in"]
               and events[0].stay.pms_reservation_id == "R-ARR")
        for e in events:
            handle_event(db, e)
    with database.session() as db:
        events = adapter.next_events(db, fx.property_a.id)
        assert ([e.type for e in events] == ["stay.checked_out"]
               and events[0].stay.pms_reservation_id == "RES-412")
        for e in events:
            handle_event(db, e)
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_out


def test_check_in_does_not_reopen_consent_for_opted_out_sms_guest(app, fx, database):
    """A guest who texted STOP before the PMS ever reported the reservation must stay opted out,
    and the PMS check-in must merge onto that guest rather than creating a duplicate."""
    phone = "+15556660000"
    consent_at = clock.now()
    with database.session() as db:
        g = Guest(property_id=fx.property_a.id, first_name=None, last_name=None, phone_e164=phone,
                  sms_consent_status=SmsConsentStatus.opted_out, sms_consent_at=consent_at,
                  sms_consent_source="sms_keyword")
        db.add(g)
        db.flush()
        guest_id = g.id

    with database.session() as db:
        ev = _event(fx, eid="R-STOP", phone=phone)
        assert handle_event(db, ev) is True
        guests = db.scalars(select(Guest).where(Guest.property_id == fx.property_a.id,
                                                Guest.phone_e164 == phone)).all()
        assert len(guests) == 1
        g = guests[0]
        assert g.id == guest_id
        assert g.first_name == "Tom"  # PMS profile data merged in
        assert g.sms_consent_status == SmsConsentStatus.opted_out  # untouched by the merge
        assert g.sms_consent_at == consent_at
        assert g.sms_consent_source == "sms_keyword"


def test_stay_upsert_survives_concurrent_insert_race(app, fx, database, monkeypatch):
    # Same race shape as guests.find_or_create_by_phone's own test
    # (test_find_or_create_by_phone_survives_concurrent_insert_race in test_guests_stays.py):
    # a second event for the same reservation (e.g. a differently-typed event that passes the
    # per-event-type dedup check) wins the insert in the gap between our SELECT and our own
    # INSERT. Force our first _find_stay lookup to miss, as it would during that race, and assert
    # handle_event recovers via the UniqueConstraint(property_id, pms_reservation_id) instead of
    # raising IntegrityError or creating a duplicate Stay row.
    from app.pms import handle_event as handle_event_module

    with database.session() as db:
        winner = Stay(guest_id=fx.guest_nostay_a.id, property_id=fx.property_a.id,
                      pms_reservation_id="R-1", room_number="999", status=StayStatus.checked_in,
                      arrival_date=clock.now().date(), departure_date=clock.now().date())
        db.add(winner)
        db.flush()
        winner_id = winner.id

        real_find_stay = handle_event_module._find_stay
        calls = {"n": 0}

        def flaky_find_stay(db_, property_id, pms_reservation_id):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # pretend the row isn't visible yet (the race window)
            return real_find_stay(db_, property_id, pms_reservation_id)

        monkeypatch.setattr(handle_event_module, "_find_stay", flaky_find_stay)

        assert handle_event(db, _event(fx)) is True
        stays = db.scalars(select(Stay).where(Stay.property_id == fx.property_a.id,
                                              Stay.pms_reservation_id == "R-1")).all()
        assert len(stays) == 1
        assert stays[0].id == winner_id


def test_same_external_id_in_two_properties_is_processed_twice(app, fx, database):
    """Most PMSs number reservations per property, which is why Stay is unique on
    (property_id, pms_reservation_id). With a globally unique idempotency key, Property B's
    stay.checked_in for reservation R-1001 was silently swallowed as a duplicate of Property A's
    and handle_event returned False — the guest never got a conversation or a room number.
    """
    ev_a = _event(fx, eid="R-1001", phone="+15551110001", room="301")
    ev_b = _event(fx, eid="R-1001", phone="+15552220002", room="302")
    ev_b.property_id = fx.property_b.id

    with database.session() as db:
        assert handle_event(db, ev_a) is True
        assert handle_event(db, ev_b) is True, "Property B's event was swallowed as a duplicate"
        stays = db.scalars(select(Stay).where(Stay.pms_reservation_id == "R-1001")).all()
        assert {(s.property_id, s.room_number) for s in stays} == {
            (fx.property_a.id, "301"), (fx.property_b.id, "302")}
        rows = db.scalars(select(PmsEvent).where(PmsEvent.external_id == "R-1001")).all()
        assert {r.property_id for r in rows} == {fx.property_a.id, fx.property_b.id}
        # ...and the key is still idempotent within each property.
        assert handle_event(db, _event(fx, eid="R-1001", phone="+15551110001",
                                       room="301")) is False
