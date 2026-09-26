"""Checklist templates (checklists spec §2.1, §3.4). Items sync through the same shared rules as
PM templates: replace-by-list, soft deletes, an item's type never changes. Categories (checklist
structure spec §3.2) save in the same request: replace-by-list with soft deletes, and each item
names its category by a request-local `key`.

Invariant: an item's `category_id` is NULL or an *active* category of its own template —
retiring a category clears it from every item that pointed at it."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, typed_items
from app.errors import NotFound, ValidationFailed
from app.models import (
    ChecklistTemplate,
    ChecklistTemplateCategory,
    ChecklistTemplateItem,
    Department,
)
from app.schemas.checklists import (
    ChecklistCategoryIn,
    ChecklistCategoryOut,
    ChecklistItemIn,
    ChecklistItemOut,
    ChecklistTemplateIn,
    ChecklistTemplateOut,
    ChecklistTemplatePatch,
)
from app.schemas.enums import ChecklistSchedule


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


def active_categories(db: Session, template_id: str) -> list[ChecklistTemplateCategory]:
    return list(db.scalars(select(ChecklistTemplateCategory).where(
        ChecklistTemplateCategory.template_id == template_id,
        ChecklistTemplateCategory.active.is_(True))
        .order_by(ChecklistTemplateCategory.position)).all())


def to_out(db: Session, t: ChecklistTemplate) -> ChecklistTemplateOut:
    dept = db.get(Department, t.department_id)
    return ChecklistTemplateOut(
        id=t.id, name=t.name, department_id=t.department_id, department_name=dept.name,
        schedule=t.schedule, shift=t.shift, weekdays=t.weekdays, active=t.active, kind=t.kind,
        categories=[ChecklistCategoryOut.model_validate(c, from_attributes=True)
                    for c in active_categories(db, t.id)],
        items=[ChecklistItemOut.model_validate(i, from_attributes=True)
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


def _check_categories(db: Session, template_id: str | None,
                      categories: list[ChecklistCategoryIn]) -> None:
    """Every refusal before any write (spec §3.2), so a 400 never leaves half a save behind."""
    keys: set[str] = set()
    ids: set[str] = set()
    for c in categories:
        if c.key in keys or (c.id is not None and c.id in ids):
            raise ValidationFailed("A category is listed twice",
                                   details={"categories": "duplicate"})
        keys.add(c.key)
        if c.id is not None:
            ids.add(c.id)
        if not c.name.strip():
            raise ValidationFailed("A category needs a name", details={"categories": "required"})
    saved = set() if template_id is None else set(db.scalars(
        select(ChecklistTemplateCategory.id).where(
            ChecklistTemplateCategory.template_id == template_id)).all())
    if ids - saved:
        raise ValidationFailed("That category is not part of this checklist",
                               details={"categories": "unknown_category"})


def _check_item_keys(items: list[ChecklistItemIn], keys: set[str]) -> None:
    if any(i.category_key is not None and i.category_key not in keys for i in items):
        raise ValidationFailed("An item names a category that is not in this checklist",
                               details={"items": "unknown_category"})


def _sync_categories(db: Session, template: ChecklistTemplate,
                     categories: list[ChecklistCategoryIn]) -> dict[str, str]:
    """Replace-by-list with soft deletes. Returns the category id for each request `key`."""
    existing = {c.id: c for c in db.scalars(select(ChecklistTemplateCategory).where(
        ChecklistTemplateCategory.template_id == template.id)).all()}
    by_key: dict[str, str] = {}
    for position, data in enumerate(categories):
        row = existing.get(data.id) if data.id else None
        if row is None:
            row = ChecklistTemplateCategory(template_id=template.id,
                                            property_id=template.property_id,
                                            name=data.name.strip(), position=position)
            db.add(row)
            db.flush()
        else:
            row.name, row.position, row.active = data.name.strip(), position, True
        by_key[data.key] = row.id
    retired = {row.id for row in existing.values() if row.id not in by_key.values()}
    for row in existing.values():
        if row.id in retired:
            row.active = False
    if retired:  # its items become ungrouped unless this same save regroups them
        for item in db.scalars(select(ChecklistTemplateItem).where(
                ChecklistTemplateItem.template_id == template.id,
                ChecklistTemplateItem.category_id.in_(retired))).all():
            item.category_id = None
    db.flush()
    return by_key


def _sync_items(db: Session, template: ChecklistTemplate, items: list[ChecklistItemIn],
                by_key: dict[str, str]) -> None:
    typed_items.sync_items(db, ChecklistTemplateItem, template, items)
    # sync_items gives the kept items positions 0..n-1 in request order and retires the rest,
    # so the active items, by position, line up one-to-one with the request.
    for row, data in zip(active_items(db, template.id), items, strict=True):
        row.category_id = by_key[data.category_key] if data.category_key else None
    db.flush()


def create(db: Session, property_id: str, actor_id: str,
           data: ChecklistTemplateIn) -> ChecklistTemplate:
    _validate_schedule(data.schedule, data.shift, data.weekdays)
    _assert_department(db, property_id, data.department_id)
    _check_categories(db, None, data.categories)
    _check_item_keys(data.items, {c.key for c in data.categories})
    t = ChecklistTemplate(property_id=property_id, name=data.name.strip(),
                          department_id=data.department_id, schedule=data.schedule,
                          shift=data.shift, weekdays=data.weekdays, active=data.active,
                          kind=data.kind)
    db.add(t)
    db.flush()
    by_key = _sync_categories(db, t, data.categories)
    _sync_items(db, t, data.items, by_key)
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
    if data.categories is not None:
        _check_categories(db, t.id, data.categories)
        keys = {c.key for c in data.categories}
    else:  # categories not sent: they stand as saved, each keyed by its own id (clarification 1)
        keys = {c.id for c in active_categories(db, t.id)}
    if data.items is not None:
        _check_item_keys(data.items, keys)
    if "department_id" in provided:
        _assert_department(db, property_id, data.department_id)
        t.department_id = data.department_id
    if "name" in provided:
        t.name = data.name.strip()
    if "active" in provided:
        t.active = data.active
    if data.kind is not None:
        t.kind = data.kind
    t.schedule, t.shift, t.weekdays = schedule, shift, weekdays
    db.flush()
    by_key = (_sync_categories(db, t, data.categories) if data.categories is not None
              else {key: key for key in keys})
    if data.items is not None:
        _sync_items(db, t, data.items, by_key)
    audit.record(db, property_id, actor_id, "checklist_template.updated", "checklist_template",
                 t.id, after={"fields": sorted(provided)})
    return t
