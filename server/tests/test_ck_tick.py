"""checklist.tick (checklists spec §3.2; plan clarification 1). FROZEN = Thu 2026-09-10 12:00
UTC = 08:00 New York (AM shift, window 11:00–19:00 UTC)."""
from datetime import UTC, datetime

from sqlalchemy import func, select

from app import clock
from app.domain import ck_instances, ck_tick
from app.models import ChecklistInstance, ChecklistTemplate, Property
from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all
from app.schemas.enums import ChecklistStatus, Role
from tests.ck_helpers import make_template

THU = 1 << 3


def _count(db):
    return db.scalar(select(func.count()).select_from(ChecklistInstance))


def test_registered_every_five_minutes():
    load_all()
    assert "checklist.tick" in HANDLERS and jobs.RECURRING["checklist.tick"] == 300


def test_generates_on_the_templates_weekdays_only_and_idempotently(database, fx, events):
    with database.session() as db:
        make_template(db, fx, name="Thursday", weekdays=THU)
        make_template(db, fx, name="Monday", weekdays=1)
        make_template(db, fx, name="Whenever", schedule="on_demand")
        assert ck_tick.tick(db) == {"generated": 1, "missed": 0}
    events.clear()
    with database.session() as db:
        assert ck_tick.tick(db) == {"generated": 0, "missed": 0}
        assert _count(db) == 1
    assert [e for e in events if e.type == ck_instances.EVENT] == []


def test_never_generates_an_already_ended_shift(database, fx):
    """Clarification 1: at 20:00 UTC the AM window (ends 19:00 UTC) is over."""
    clock.freeze(datetime(2026, 9, 10, 20, 0, tzinfo=UTC))
    with database.session() as db:
        make_template(db, fx, shift="am")
        make_template(db, fx, name="PM", shift="pm")
        assert ck_tick.tick(db) == {"generated": 1, "missed": 0}


def test_marks_missed_exactly_when_the_window_ends(database, fx):
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
    clock.freeze(datetime(2026, 9, 10, 18, 59, tzinfo=UTC))
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 0
    clock.freeze(datetime(2026, 9, 10, 19, 0, tzinfo=UTC))
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 1
        assert db.scalar(select(ChecklistInstance.status)) is ChecklistStatus.missed


def test_complete_instances_are_left_alone(database, fx):
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        inst = db.scalar(select(ChecklistInstance))
        inst.status = ChecklistStatus.complete
    clock.freeze(datetime(2026, 9, 10, 23, 0, tzinfo=UTC))
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 0


def test_missed_uses_current_boundaries(database, fx):
    """Review focus 1: moving the pm boundary later extends an in-flight AM instance."""
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        p = db.get(Property, fx.property_a.id)
        p.settings = {**(p.settings or {}), "shift_boundaries": {"pm": "16:00"}}
    clock.freeze(datetime(2026, 9, 10, 19, 30, tzinfo=UTC))  # past 15:00 local, before 16:00
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 0


def test_deactivated_template_keeps_todays_instance(database, fx):
    """Review focus 2."""
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        db.scalar(select(ChecklistTemplate)).active = False
    with database.session() as db:
        ck_tick.tick(db)
        assert db.scalar(select(ChecklistInstance.status)) is ChecklistStatus.open


def test_a_partly_answered_instance_is_frozen_as_missed(database, fx):
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        inst = db.scalar(select(ChecklistInstance))
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
    clock.freeze(datetime(2026, 9, 10, 19, 0, tzinfo=UTC))
    with database.session() as db:
        ck_tick.tick(db)
        assert db.scalar(select(ChecklistInstance.status)) is ChecklistStatus.missed
