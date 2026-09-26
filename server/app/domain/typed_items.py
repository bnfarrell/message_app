"""Typed checklist items shared by preventative maintenance and shift checklists.

Items and answers are duck-typed: PmTemplateItem / ChecklistTemplateItem and PmRunAnswer /
ChecklistAnswer carry the same columns, so one set of rules serves both — a fix here fixes both.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import ValidationFailed
from app.models import PropertyMembership, UserAccount
from app.schemas.enums import PmItemType, Role, UserStatus
from app.schemas.pm import AnswerPatch, TemplateItemIn

VALUE_COLUMN: dict[PmItemType, str] = {
    PmItemType.checkbox: "bool_value",
    PmItemType.text: "text_value",
    PmItemType.number: "number_value",
}
WIRE_NAME = {"bool_value": "boolValue", "text_value": "textValue", "number_value": "numberValue"}


def apply_answer(item: Any, answer: Any, data: AnswerPatch) -> None:
    """Validate a typed answer and write it onto `answer`, stamping answered_at and out_of_range."""
    column = VALUE_COLUMN.get(item.item_type)
    if column is None:
        raise ValidationFailed("A photo item is answered by uploading a photo",
                               details={"itemId": "photo_item"})
    provided = data.model_dump(exclude_unset=True)
    if set(provided) != {column}:
        raise ValidationFailed(f"This item takes {WIRE_NAME[column]} only",
                               details={WIRE_NAME[column]: "required"})
    value = provided[column]
    if column == "text_value" and value is not None:
        value = value.strip() or None
    setattr(answer, column, value)
    answer.answered_at = clock.now() if value is not None else None
    if item.item_type == PmItemType.number:
        answer.out_of_range = value is not None and (
            (item.min_value is not None and value < item.min_value)
            or (item.max_value is not None and value > item.max_value))


def is_answered(item: Any, answer: Any, photographed: set[str]) -> bool:
    """A required checkbox must be ticked, not merely answered; a photo item is satisfied by a
    photo carrying its id."""
    if item.item_type == PmItemType.checkbox:
        return answer.bool_value is True
    if item.item_type == PmItemType.text:
        return bool(answer.text_value)
    if item.item_type == PmItemType.number:
        return answer.number_value is not None
    return item.id in photographed


def sync_items(db: Session, item_model: type, template: Any, items: list[TemplateItemIn]) -> None:
    """Replace-by-list with soft deletes: an item in the list is updated or created in its
    position; one missing from it is deactivated. Type never changes on an existing item —
    answers already recorded against it would mean something else."""
    existing = {i.id: i for i in db.scalars(select(item_model).where(
        item_model.template_id == template.id)).all()}
    seen_ids: set[str] = set()
    for data in items:
        if data.id:
            if data.id in seen_ids:
                raise ValidationFailed("Duplicate item id", details={"items": "duplicate_item"})
            seen_ids.add(data.id)
    keep: set[str] = set()
    for position, data in enumerate(items):
        if data.item_type != PmItemType.number and (
                data.min_value is not None or data.max_value is not None or data.unit):
            raise ValidationFailed("Bounds and units apply to number items only",
                                   details={"items": "bounds_on_non_number"})
        if (data.min_value is not None and data.max_value is not None
                and data.min_value > data.max_value):
            raise ValidationFailed("Minimum must not exceed maximum",
                                   details={"items": "min_over_max"})
        if data.id:
            row = existing.get(data.id)
            if row is None:
                raise ValidationFailed("Unknown item", details={"items": "unknown_item"})
            if row.item_type != data.item_type:
                raise ValidationFailed("An item's type cannot change; remove it and add a new one",
                                       details={"items": "type_change"})
            row.position, row.label, row.unit = position, data.label.strip(), data.unit
            row.min_value, row.max_value = data.min_value, data.max_value
            row.required, row.active = data.required, True
        else:
            row = item_model(template_id=template.id, property_id=template.property_id,
                             position=position, label=data.label.strip(),
                             item_type=data.item_type, unit=data.unit,
                             min_value=data.min_value, max_value=data.max_value,
                             required=data.required)
            db.add(row)
            db.flush()
        keep.add(row.id)
    retired = [row for row in existing.values() if row.id not in keep]
    for n, row in enumerate(retired):
        # Pushed past the live range so a retired item never shares a position with a kept one —
        # historical runs render their answers `order_by(position)`.
        row.active = False
        row.position = 1000 + n
    db.flush()


def escalation_targets(db: Session, property_id: str, department_id: str | None) -> list[str]:
    """Active supervisor-or-above members of the department; failing that, the property's
    managers and admins, so an out-of-range reading is never reported to nobody."""
    stmt = (select(PropertyMembership.user_id)
            .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
            .where(PropertyMembership.property_id == property_id,
                   UserAccount.status == UserStatus.active))
    if department_id:
        scoped = list(db.scalars(stmt.where(
            PropertyMembership.department_id == department_id,
            PropertyMembership.role.in_([Role.supervisor, Role.manager, Role.admin]))).all())
        if scoped:
            return scoped
    return list(db.scalars(stmt.where(
        PropertyMembership.role.in_([Role.manager, Role.admin]))).all())


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def out_of_range_title(item: Any, answer: Any, where: str) -> str:
    return (f"{item.label} {fmt(answer.number_value)}{item.unit or ''} out of range "
            f"({fmt(item.min_value)}–{fmt(item.max_value)}) — {where}")[:200]
