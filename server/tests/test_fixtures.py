from sqlalchemy import func, select

from app.models import Guest, PropertyMembership, UserAccount


def test_fixture_loads_two_properties_and_users(app, fx, database):
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount)) == 11
        assert db.scalar(select(func.count()).select_from(PropertyMembership)) == 11
        assert db.scalar(select(func.count()).select_from(Guest)) == 3
    assert fx.property_a.id != fx.property_b.id
    assert fx.stay_inhouse_a.room_number == "412"


def test_clock_is_frozen(app):
    from app import clock

    assert clock.now().isoformat() == "2026-09-10T12:00:00+00:00"


def test_each_test_gets_a_fresh_database(app, database):
    """The entry assertion is the real check: a leaked row from a prior run would fail it."""
    from app.models import Property

    with database.session() as db:
        assert db.scalar(select(Property).where(Property.code == "SCR")) is None
        db.add(Property(name="Scratch", code="SCR", timezone="UTC"))
    with database.session() as db:
        assert db.scalar(select(Property).where(Property.code == "SCR")) is not None
