"""Checklist templates (checklists spec §2.1, §3.4). Items sync through the same shared rules as
PM templates: replace-by-list, soft deletes, an item's type never changes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, typed_items
from app.errors import NotFound, ValidationFailed
from app.models import ChecklistTemplate, ChecklistTemplateItem, Department
from app.schemas.checklists import ChecklistTemplateIn, ChecklistTemplateOut, ChecklistTemplatePatch
from app.schemas.enums import ChecklistSchedule
from app.schemas.pm import TemplateItemOut


def get(db: Session, property_id: str, template_id: str) -> ChecklistTemplate:
    t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.id == template_id,
                                                  ChecklistTemplate.property_id == property_id))
    if t is None:
        raise NotFound("Checklist template not found")
    return t


def active_items(db: Session, template_id: str) -> list[ChecklistTemplateItem]:
    return list(db.scalars(select(ChecklistTemplateItem).where(
        ChecklistTemplateItem.template_id == template_id,
        ChecklistTemplateItem.active.is_(True)).order_by(ChecklistTemplateItem.position)).all())


def to_out(db: Session, t: ChecklistTemplate) -> ChecklistTemplateOut:
    dept = db.get(Department, t.department_id)
    return ChecklistTemplateOut(
        id=t.id, name=t.name, department_id=t.department_id, department_name=dept.name,
        schedule=t.schedule, shift=t.shift, weekdays=t.weekdays, active=t.active,
        items=[TemplateItemOut.model_validate(i, from_attributes=True)
               for i in active_items(db, t.id)])


def list_templates(db: Session, property_id: str) -> list[ChecklistTemplateOut]:
    rows = db.scalars(select(ChecklistTemplate).where(ChecklistTemplate.property_id == property_id)
                      .order_by(ChecklistTemplate.name, ChecklistTemplate.id)).all()
    return [to_out(db, t) for t in rows]


def _validate_schedule(schedule, shift, weekdays) -> None:
    if schedule == ChecklistSchedule.weekly and (shift is None or not weekdays):
        raise ValidationFailed("A weekly checklist needs a shift and at least one day",
                               details={"weekdays": "required"})
    if schedule == ChecklistSchedule.on_demand and (shift is not None or weekdays is not None):
        raise ValidationFailed("An on-demand checklist has no shift or days — it takes the shift "
                               "it is started in", details={"shift": "not_allowed"})
    if schedule == ChecklistSchedule.unscheduled and (shift is not None or weekdays is not None):
        raise ValidationFailed("An unscheduled checklist has no shift or days yet",
                               details={"shift": "not_allowed"})


def _assert_department(db: Session, property_id: str, department_id: str) -> None:
    if db.scalar(select(Department.id).where(Department.id == department_id,
                                             Department.property_id == property_id)) is None:
        raise ValidationFailed("Unknown department", details={"departmentId": "unknown"})


def create(db: Session, property_id: str, actor_id: str,
           data: ChecklistTemplateIn) -> ChecklistTemplate:
    _validate_schedule(data.schedule, data.shift, data.weekdays)
    _assert_department(db, property_id, data.department_id)
    t = ChecklistTemplate(property_id=property_id, name=data.name.strip(),
                          department_id=data.department_id, schedule=data.schedule,
                          shift=data.shift, weekdays=data.weekdays, active=data.active)
    db.add(t)
    db.flush()
    typed_items.sync_items(db, ChecklistTemplateItem, t, data.items)
    audit.record(db, property_id, actor_id, "checklist_template.created", "checklist_template",
                 t.id, after={"name": t.name})
    return t


def patch(db: Session, property_id: str, actor_id: str, template_id: str,
          data: ChecklistTemplatePatch) -> ChecklistTemplate:
    t = get(db, property_id, template_id)
    provided = data.model_dump(exclude_unset=True)
    schedule = provided.get("schedule", t.schedule)
    shift = provided["shift"] if "shift" in provided else t.shift
    weekdays = provided["weekdays"] if "weekdays" in provided else t.weekdays
    _validate_schedule(schedule, shift, weekdays)
    if "department_id" in provided:
        _assert_department(db, property_id, data.department_id)
        t.department_id = data.department_id
    if "name" in provided:
        t.name = data.name.strip()
    if "active" in provided:
        t.active = data.active
    t.schedule, t.shift, t.weekdays = schedule, shift, weekdays
    db.flush()
    if data.items is not None:
        typed_items.sync_items(db, ChecklistTemplateItem, t, data.items)
    audit.record(db, property_id, actor_id, "checklist_template.updated", "checklist_template",
                 t.id, after={"fields": sorted(provided)})
    return t
