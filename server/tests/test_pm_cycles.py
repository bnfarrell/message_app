"""Cycle windows (spec §3.5, §4.1 phase A)."""
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app import clock
from app.domain import pm_cycles
from app.models import MaintainableUnit, PmCycle, PmRun, PmTemplate, Property
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
)


def test_window_for_aligns_to_the_calendar_year():
    assert pm_cycles.window_for(PmCadence.quarterly, date(2026, 9, 10)) == (
        date(2026, 7, 1), date(2026, 9, 30), 3)
    assert pm_cycles.window_for(PmCadence.quarterly, date(2026, 12, 31)) == (
        date(2026, 10, 1), date(2026, 12, 31), 4)
    assert pm_cycles.window_for(PmCadence.quarterly, date(2026, 1, 1)) == (
        date(2026, 1, 1), date(2026, 3, 31), 1)
    assert pm_cycles.window_for(PmCadence.monthly, date(2028, 2, 15)) == (
        date(2028, 2, 1), date(2028, 2, 29), 2)  # leap year
    assert pm_cycles.window_for(PmCadence.semiannual, date(2026, 7, 1)) == (
        date(2026, 7, 1), date(2026, 12, 31), 2)
    assert pm_cycles.window_for(PmCadence.annual, date(2026, 6, 6)) == (
        date(2026, 1, 1), date(2026, 12, 31), 1)


def test_local_today_uses_the_property_timezone(database, fx):
    with database.session() as db:
        prop = db.get(Property, fx.property_a.id)  # America/New_York
        # 02:00 UTC on the 11th is still the 10th in New York.
        assert pm_cycles.local_today(prop, datetime(2026, 9, 11, 2, 0, tzinfo=UTC)) == \
            date(2026, 9, 10)
        assert pm_cycles.local_day_start_utc(prop, date(2026, 9, 10)) == \
            datetime(2026, 9, 10, 4, 0, tzinfo=UTC)  # EDT is UTC-4


def _sweep(db, fx, active=True):
    t = PmTemplate(property_id=fx.property_a.id, name="Rooms", mode=PmTemplateMode.sweep,
                   unit_kind=PmUnitKind.guest_room, cadence=PmCadence.quarterly, active=active)
    db.add(t)
    db.flush()
    return t


def _unit(db, fx, code, kind=PmUnitKind.guest_room, active=True):
    u = MaintainableUnit(property_id=fx.property_a.id, kind=kind, code=code, name=code,
                         active=active)
    db.add(u)
    db.flush()
    return u


def test_ensure_open_cycle_opens_once_for_today_and_only_for_active_sweeps(database, fx, events):
    with database.session() as db:
        t = _sweep(db, fx)
        cycle = pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10))
        assert (cycle.ordinal, cycle.starts_on, cycle.ends_on) == (
            3, date(2026, 7, 1), date(2026, 9, 30))
        assert cycle.status == PmCycleStatus.open
        assert pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10)) is None
        assert pm_cycles.ensure_open_cycle(db, t, date(2026, 10, 1)) is None, \
            "an open cycle blocks a second, even an expired one — close_expired goes first"
        inactive = _sweep(db, fx, active=False)
        assert pm_cycles.ensure_open_cycle(db, inactive, date(2026, 9, 10)) is None
    assert any(e.type == "pm.cycle.rolled" for e in events)


def test_scope_is_every_active_unit_of_the_kind(database, fx):
    with database.session() as db:
        t = _sweep(db, fx)
        a = _unit(db, fx, "201")
        _unit(db, fx, "202", active=False)
        _unit(db, fx, "LOBBY", kind=PmUnitKind.common_area)
        assert pm_cycles.scope_unit_ids(db, t) == [a.id]


def test_close_expired_freezes_a_missed_run_per_unswept_active_unit_once(database, fx):
    with database.session() as db:
        t = _sweep(db, fx)
        cycle = pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10))
        swept = _unit(db, fx, "201")
        _unit(db, fx, "202")
        _unit(db, fx, "203")
        _unit(db, fx, "204", active=False)
        db.add(PmRun(property_id=fx.property_a.id, template_id=t.id, unit_id=swept.id,
                     cycle_id=cycle.id, status=PmRunStatus.passed,
                     started_by_user_id=fx.engineer_a.id, started_at=clock.now(),
                     completed_at=clock.now(), inspected_at=clock.now()))
        db.flush()
        assert pm_cycles.close_expired(db, t, date(2026, 9, 30)) == 0, "still inside the window"
        assert pm_cycles.close_expired(db, t, date(2026, 10, 1)) == 2
        assert db.get(PmCycle, cycle.id).status == PmCycleStatus.closed
        missed = db.scalars(select(PmRun.unit_id).where(
            PmRun.cycle_id == cycle.id, PmRun.status == PmRunStatus.missed)).all()
        assert swept.id not in missed and len(missed) == 2
        assert pm_cycles.close_expired(db, t, date(2026, 10, 1)) == 0, "idempotent"
        assert db.scalar(select(func.count()).select_from(PmRun)) == 3
        # And the next window opens cleanly afterwards.
        nxt = pm_cycles.ensure_open_cycle(db, t, date(2026, 10, 1))
        assert (nxt.ordinal, nxt.starts_on) == (4, date(2026, 10, 1))


def test_inactive_template_neither_closes_nor_opens(database, fx):
    with database.session() as db:
        t = _sweep(db, fx)
        pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10))
        t.active = False
        db.flush()
        assert pm_cycles.close_expired(db, t, date(2027, 1, 1)) == 0
        assert pm_cycles.open_cycle(db, t).status == PmCycleStatus.open
