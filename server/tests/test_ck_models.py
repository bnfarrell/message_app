"""Shift-checklist schema (checklists spec §2, §6)."""
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import ChecklistInstance, ChecklistTemplate
from app.schemas.enums import ChecklistSchedule, ChecklistStatus, Shift

SERVER = Path(__file__).resolve().parent.parent


def _template(db, fx, **kw):
    t = ChecklistTemplate(property_id=fx.property_a.id, name="AM Rounds",
                          department_id=fx.dept_engineering.id, **kw)
    db.add(t)
    db.flush()
    return t


def test_weekly_template_needs_a_shift_and_weekdays(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.weekly, shift=Shift.am, weekdays=None)
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.weekly, shift=Shift.am, weekdays=0)


def test_on_demand_template_has_neither_shift_nor_weekdays(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.on_demand, shift=Shift.am, weekdays=None)
    with database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.on_demand, shift=None, weekdays=None)


def _instance(db, t, slot):
    db.add(ChecklistInstance(property_id=t.property_id, template_id=t.id,
                             due_date=date(2026, 9, 10), shift=Shift.am, slot=slot,
                             status=ChecklistStatus.open))
    db.flush()


def test_scheduled_slot_is_unique_but_on_demand_slots_repeat(database, fx):
    with database.session() as db:
        t = _template(db, fx, schedule=ChecklistSchedule.weekly, shift=Shift.am, weekdays=127)
        _instance(db, t, None)
        _instance(db, t, None)  # NULLs are distinct: on-demand may repeat
        _instance(db, t, 0)
        tid = t.id
    with pytest.raises(IntegrityError), database.session() as db:
        _instance(db, db.get(ChecklistTemplate, tid), 0)


def test_0009_downgrades_and_reupgrades(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    assert "checklist_instance" in sa.inspect(engine).get_table_names()
    command.downgrade(cfg, "0008")
    assert "checklist_template" not in sa.inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "checklist_photo" in sa.inspect(engine).get_table_names()
    engine.dispose()
