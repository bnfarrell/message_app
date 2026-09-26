"""Checklist read models (checklists spec §4.2, §4.4)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import ck_instances, ck_photos, ck_templates, pm_cycles, shifts, typed_items
from app.domain.pm_runs import names_for
from app.models import (
    ChecklistAnswer,
    ChecklistInstance,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Department,
    Property,
)
from app.schemas.checklists import (
    ChecklistCategoryProgressOut,
    ChecklistInstanceOut,
    ChecklistInstanceQuery,
    ChecklistInstanceRowOut,
    ChecklistItemOut,
    ChecklistMissedQuery,
)
from app.schemas.enums import ChecklistStatus, Shift
from app.schemas.pm import RunAnswerOut, RunPhotoOut

SHIFT_ORDER = {Shift.am: 0, Shift.pm: 1, Shift.overnight: 2}


def _answered_rows(db: Session, inst: ChecklistInstance):
    return db.execute(select(ChecklistAnswer, ChecklistTemplateItem)
                      .join(ChecklistTemplateItem,
                            ChecklistTemplateItem.id == ChecklistAnswer.item_id)
                      .where(ChecklistAnswer.instance_id == inst.id)
                      .order_by(ChecklistTemplateItem.position)).all()


def _progress(db: Session, inst: ChecklistInstance) -> tuple[int, int, int]:
    """(done, total, out_of_range) — clarification 4. An unstarted instance counts the template's
    active items; a started one its own snapshot."""
    rows = _answered_rows(db, inst)
    if not rows:
        return 0, len(ck_templates.active_items(db, inst.template_id)), 0
    photographed = {p.item_id for p in ck_photos.photos_for(db, inst.id) if p.item_id}
    done = sum(typed_items.is_answered(item, answer, photographed) for answer, item in rows)
    return done, len(rows), sum(answer.out_of_range for answer, _ in rows)


def _row_fields(db: Session, inst, template, dept, names) -> dict:
    done, total, oor = _progress(db, inst)
    return dict(
        id=inst.id, template_id=template.id, template_name=template.name,
        department_id=dept.id, department_name=dept.name, due_date=inst.due_date,
        shift=inst.shift, on_demand=inst.slot is None, status=inst.status, kind=template.kind,
        assigned_user_id=inst.assigned_user_id,
        assigned_name=names.get(inst.assigned_user_id or ""),
        completed_by_name=names.get(inst.completed_by_user_id or ""),
        done=done, total=total, out_of_range_count=oor)


def _joined(property_id: str):
    return (select(ChecklistInstance, ChecklistTemplate, Department)
            .join(ChecklistTemplate, ChecklistTemplate.id == ChecklistInstance.template_id)
            .join(Department, Department.id == ChecklistTemplate.department_id)
            .where(ChecklistInstance.property_id == property_id))


def _rows(db: Session, triples) -> list[ChecklistInstanceRowOut]:
    names = names_for(db, [i.assigned_user_id for i, _, _ in triples]
                      + [i.completed_by_user_id for i, _, _ in triples])
    return [ChecklistInstanceRowOut(**_row_fields(db, i, t, d, names)) for i, t, d in triples]


def list_instances(db: Session, property_id: str,
                   query: ChecklistInstanceQuery) -> list[ChecklistInstanceRowOut]:
    prop = db.get(Property, property_id)
    day = query.day or shifts.current_shift(prop, clock.now())[0]
    stmt = _joined(property_id).where(ChecklistInstance.due_date == day)
    if query.department_id:
        stmt = stmt.where(ChecklistTemplate.department_id == query.department_id)
    if query.status:
        stmt = stmt.where(ChecklistInstance.status == query.status)
    triples = sorted(db.execute(stmt).all(),
                     key=lambda r: (SHIFT_ORDER[r[0].shift], r[1].name, r[0].created_at))
    return _rows(db, triples)


def missed(db: Session, property_id: str,
           query: ChecklistMissedQuery) -> list[ChecklistInstanceRowOut]:
    since = pm_cycles.local_today(db.get(Property, property_id)) - timedelta(days=query.days - 1)
    triples = sorted(db.execute(_joined(property_id).where(
        ChecklistInstance.status == ChecklistStatus.missed,
        ChecklistInstance.due_date >= since)).all(),
        key=lambda r: (-r[0].due_date.toordinal(), SHIFT_ORDER[r[0].shift], r[1].name))
    return _rows(db, triples)


def _category_progress(db: Session, template: ChecklistTemplate, items, rows,
                       photographed: set[str]) -> list[ChecklistCategoryProgressOut]:
    """One heading per active category that holds any of this checklist's items, in category
    order (checklist structure spec §2.2). Ungrouped items belong to no heading. An unstarted
    checklist has no answers yet, so everything counts as not done."""
    answer_for = {item.id: answer for answer, item in rows}
    out = []
    for category in ck_templates.active_categories(db, template.id):
        members = [i for i in items if i.category_id == category.id]
        if not members:
            continue
        done = sum(1 for i in members if i.id in answer_for
                   and typed_items.is_answered(i, answer_for[i.id], photographed))
        out.append(ChecklistCategoryProgressOut(id=category.id, name=category.name,
                                                position=category.position, done=done,
                                                total=len(members)))
    return out


def detail(db: Session, property_id: str, instance_id: str) -> ChecklistInstanceOut:
    inst = ck_instances.get(db, property_id, instance_id)
    template = db.get(ChecklistTemplate, inst.template_id)
    dept = db.get(Department, template.department_id)
    names = names_for(db, [inst.assigned_user_id, inst.completed_by_user_id,
                           inst.started_by_user_id])
    rows = _answered_rows(db, inst)
    items = [item for _, item in rows] or ck_templates.active_items(db, template.id)
    photos = ck_photos.photos_for(db, inst.id)
    photographed = {p.item_id for p in photos if p.item_id}
    return ChecklistInstanceOut(
        **_row_fields(db, inst, template, dept, names),
        started_by_name=names.get(inst.started_by_user_id or ""), started_at=inst.started_at,
        completed_at=inst.completed_at, comment=inst.comment,
        categories=_category_progress(db, template, items, rows, photographed),
        items=[ChecklistItemOut.model_validate(i, from_attributes=True) for i in items],
        answers=[RunAnswerOut.model_validate(a, from_attributes=True) for a, _ in rows],
        photos=[RunPhotoOut(id=p.id, item_id=p.item_id, content_type=p.content_type,
                            byte_size=p.byte_size, uploaded_by_user_id=p.uploaded_by_user_id,
                            url=ck_photos.photo_url(property_id, inst.id, p.id),
                            created_at=p.created_at) for p in photos],
        missing_required=(ck_instances.missing_required(db, inst)
                          if inst.status == ChecklistStatus.in_progress else []))
