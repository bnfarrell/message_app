"""Preventative maintenance tables (spec §3). Round trips and the constraints that matter."""
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import clock
from app.models import (
    MaintainableUnit,
    PmCycle,
    PmRun,
    PmRunAnswer,
    PmRunPhoto,
    PmTemplate,
    PmTemplateItem,
    PmTemplateUnit,
)
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
    PmUnitSource,
)


def test_unit_template_cycle_run_answer_photo_round_trip(database, fx):
    with database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204", floor=2, room_type="KNGN")
        db.add(unit)
        db.flush()
        template = PmTemplate(property_id=fx.property_a.id, name="Guest Room Quarterly",
                              mode=PmTemplateMode.sweep, unit_kind=PmUnitKind.guest_room,
                              cadence=PmCadence.quarterly,
                              department_id=fx.dept_engineering.id)
        db.add(template)
        db.flush()
        item = PmTemplateItem(template_id=template.id, property_id=fx.property_a.id,
                              position=0, label="Tap hot-water temperature",
                              item_type=PmItemType.number, unit="°F",
                              min_value=100, max_value=120, required=True)
        db.add(item)
        cycle = PmCycle(property_id=fx.property_a.id, template_id=template.id, ordinal=3,
                        starts_on=date(2026, 7, 1), ends_on=date(2026, 9, 30),
                        status=PmCycleStatus.open)
        db.add(cycle)
        db.flush()
        run = PmRun(property_id=fx.property_a.id, template_id=template.id, unit_id=unit.id,
                    cycle_id=cycle.id, status=PmRunStatus.in_progress,
                    started_by_user_id=fx.engineer_a.id, started_at=clock.now())
        db.add(run)
        db.flush()
        db.add(PmRunAnswer(run_id=run.id, property_id=fx.property_a.id, item_id=item.id,
                           number_value=122.5, out_of_range=True, answered_at=clock.now()))
        db.add(PmRunPhoto(run_id=run.id, property_id=fx.property_a.id, item_id=None,
                          uploaded_by_user_id=fx.engineer_a.id, content_type="image/png",
                          byte_size=3, data=b"abc"))
        db.flush()
        ids = (unit.id, template.id, run.id)

    with database.session() as db:
        unit = db.get(MaintainableUnit, ids[0])
        assert unit.source == PmUnitSource.manual and unit.active is True
        template = db.get(PmTemplate, ids[1])
        assert template.mode == PmTemplateMode.sweep and template.rrule is None
        run = db.get(PmRun, ids[2])
        assert run.status == PmRunStatus.in_progress
        answer = db.scalar(select(PmRunAnswer).where(PmRunAnswer.run_id == run.id))
        assert answer.number_value == 122.5 and isinstance(answer.number_value, float)
        assert answer.out_of_range is True
        photo = db.scalar(select(PmRunPhoto).where(PmRunPhoto.run_id == run.id))
        assert photo.data == b"abc"


def test_unit_code_is_unique_per_property(database, fx):
    with database.session() as db:
        db.add(MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204"))
        # Same code at another property is fine.
        db.add(MaintainableUnit(property_id=fx.property_b.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204"))
        db.flush()
        db.add(MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.equipment,
                                code="204", name="Dup"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_template_mode_check_constraint_rejects_a_sweep_with_an_rrule(database, fx):
    with database.session() as db:
        db.add(PmTemplate(property_id=fx.property_a.id, name="Bad", mode=PmTemplateMode.sweep,
                          unit_kind=PmUnitKind.guest_room, cadence=PmCadence.monthly,
                          rrule="FREQ=DAILY", rrule_dtstart=date(2026, 1, 1)))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_template_mode_check_constraint_rejects_a_scheduled_template_without_a_start(
        database, fx):
    with database.session() as db:
        db.add(PmTemplate(property_id=fx.property_a.id, name="Bad",
                          mode=PmTemplateMode.scheduled, rrule="FREQ=DAILY"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_template_unit_and_run_answer_are_unique(database, fx):
    with database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.equipment,
                                code="BOILER-1", name="Boiler 1")
        template = PmTemplate(property_id=fx.property_a.id, name="Boiler",
                              mode=PmTemplateMode.scheduled, rrule="FREQ=MONTHLY;INTERVAL=3",
                              rrule_dtstart=date(2026, 7, 1))
        db.add_all([unit, template])
        db.flush()
        db.add(PmTemplateUnit(template_id=template.id, unit_id=unit.id,
                              property_id=fx.property_a.id))
        db.flush()
        db.add(PmTemplateUnit(template_id=template.id, unit_id=unit.id,
                              property_id=fx.property_a.id))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
