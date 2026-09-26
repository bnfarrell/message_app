"""Hotel log post templates (log templates spec §2, §3).

Fields sync replace-by-list with soft deletes, like checklist items, but through their own rules
rather than app.domain.typed_items: the field types are not PM's item types, and there are no
bounds or units. A saved field's type never changes — value rows already posted against it would
mean something else.
"""
from __future__ import annotations

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, shifts
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import (
    Department,
    LogEntry,
    LogEntryFieldValue,
    LogTemplate,
    LogTemplateAudience,
    LogTemplateField,
    Property,
    PropertyMembership,
)
from app.schemas.enums import LogFieldType, MentionTargetType, Role
from app.schemas.log import (
    MAX_BODY,
    LogFieldValueIn,
    LogTemplateFieldIn,
    LogTemplateFieldOut,
    LogTemplateIn,
    LogTemplateOut,
    LogTemplatePatch,
    MentionRef,
)

# Spec §3.1: these roles may use any template, whatever its audience.
EXEMPT_ROLES = {Role.manager, Role.admin, Role.corporate}


def get(db: Session, property_id: str, template_id: str) -> LogTemplate:
    t = db.scalar(select(LogTemplate).where(LogTemplate.id == template_id,
                                            LogTemplate.property_id == property_id))
    if t is None:
        raise NotFound("Log template not found")
    return t


def active_fields(db: Session, template_id: str) -> list[LogTemplateField]:
    return list(db.scalars(select(LogTemplateField).where(
        LogTemplateField.template_id == template_id,
        LogTemplateField.active.is_(True)).order_by(LogTemplateField.position)).all())


def _audiences(db: Session, template_ids: list[str]) -> dict[str, list[MentionRef]]:
    out: dict[str, list[MentionRef]] = {tid: [] for tid in template_ids}
    for row in db.scalars(select(LogTemplateAudience)
                          .where(LogTemplateAudience.template_id.in_(template_ids))
                          .order_by(LogTemplateAudience.type, LogTemplateAudience.target_id)):
        out[row.template_id].append(MentionRef(type=row.type, id=row.target_id))
    return out


def _membership(db: Session, property_id: str, user_id: str) -> PropertyMembership | None:
    return db.scalar(select(PropertyMembership).where(
        PropertyMembership.property_id == property_id, PropertyMembership.user_id == user_id))


def _allowed(membership: PropertyMembership | None, audience: list[MentionRef]) -> bool:
    """Spec §3.1: an empty audience is everyone; otherwise a listed user, a member of a listed
    department, or an exempt role."""
    if membership is None:
        return False
    if not audience or membership.role in EXEMPT_ROLES:
        return True
    for ref in audience:
        if ref.type == MentionTargetType.user and ref.id == membership.user_id:
            return True
        if (ref.type == MentionTargetType.department and membership.department_id is not None
                and ref.id == membership.department_id):
            return True
    return False


def assert_can_use(db: Session, property_id: str, user_id: str, template: LogTemplate) -> None:
    if not _allowed(_membership(db, property_id, user_id),
                    _audiences(db, [template.id])[template.id]):
        raise Forbidden("This template is not shared with you")


def _outs(db: Session, property_id: str, templates: list[LogTemplate]) -> list[LogTemplateOut]:
    """One pass over a list of templates, batching fields, audiences and usage counts."""
    ids = [t.id for t in templates]
    if not ids:
        return []
    fields: dict[str, list[LogTemplateFieldOut]] = {tid: [] for tid in ids}
    for f in db.scalars(select(LogTemplateField)
                        .where(LogTemplateField.template_id.in_(ids),
                               LogTemplateField.active.is_(True))
                        .order_by(LogTemplateField.position)):
        fields[f.template_id].append(LogTemplateFieldOut.model_validate(f, from_attributes=True))
    audiences = _audiences(db, ids)
    used = dict(db.execute(
        select(LogEntry.template_id, func.count())
        .where(LogEntry.property_id == property_id, LogEntry.template_id.in_(ids))
        .group_by(LogEntry.template_id)).all())
    return [LogTemplateOut(id=t.id, name=t.name, shift=t.shift, active=t.active,
                           position=t.position, fields=fields[t.id], audience=audiences[t.id],
                           used_count=used.get(t.id, 0))
            for t in templates]


def to_out(db: Session, t: LogTemplate) -> LogTemplateOut:
    return _outs(db, t.property_id, [t])[0]


def _name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise ValidationFailed("A template needs a name", details={"name": "required"})
    return name


def _clean_audience(db: Session, property_id: str, refs: list[MentionRef]) -> list[MentionRef]:
    """De-duplicated (the table's unique key would otherwise turn a repeat into a 500) and
    scoped: every user must be a member here and every department must be this property's."""
    out: list[MentionRef] = []
    for type_, target_id in dict.fromkeys((r.type, r.id) for r in refs):
        if type_ == MentionTargetType.user:
            known = _membership(db, property_id, target_id) is not None
        else:
            known = db.scalar(select(Department.id).where(
                Department.id == target_id, Department.property_id == property_id)) is not None
        if not known:
            raise ValidationFailed("Share a template only with people and departments here",
                                   details={"audience": f"unknown_{type_.value}"})
        out.append(MentionRef(type=type_, id=target_id))
    return out


def _replace_audience(db: Session, template: LogTemplate, refs: list[MentionRef]) -> None:
    for row in db.scalars(select(LogTemplateAudience)
                          .where(LogTemplateAudience.template_id == template.id)).all():
        db.delete(row)
    # Flush the deletes before the inserts: in one flush SQLAlchemy inserts first, and a ref kept
    # across the save would then collide with its own old row on the unique key.
    db.flush()
    for ref in refs:
        db.add(LogTemplateAudience(template_id=template.id, property_id=template.property_id,
                                   type=ref.type, target_id=ref.id))
    db.flush()


def _sync_fields(db: Session, template: LogTemplate, fields: list[LogTemplateFieldIn]) -> None:
    """Replace-by-list with soft deletes: a field in the list is updated or created in its
    position; a saved field missing from it is deactivated."""
    existing = {f.id: f for f in db.scalars(select(LogTemplateField).where(
        LogTemplateField.template_id == template.id)).all()}
    seen: set[str] = set()
    for data in fields:
        if not data.label.strip():
            raise ValidationFailed("Every field needs a label", details={"fields": "required"})
        if data.id:
            if data.id in seen:
                raise ValidationFailed("Duplicate field id", details={"fields": "duplicate_field"})
            seen.add(data.id)
    keep: set[str] = set()
    for position, data in enumerate(fields):
        if data.id:
            row = existing.get(data.id)
            if row is None:
                raise ValidationFailed("Unknown field", details={"fields": "unknown_field"})
            if row.field_type != data.field_type:
                raise ValidationFailed("A field's type cannot change; remove it and add a new one",
                                       details={"fields": "type_change"})
            row.position, row.label = position, data.label.strip()
            row.required, row.active = data.required, True
        else:
            row = LogTemplateField(template_id=template.id, property_id=template.property_id,
                                   position=position, label=data.label.strip(),
                                   field_type=data.field_type, required=data.required)
            db.add(row)
            db.flush()
        keep.add(row.id)
    retired = sorted((row for row in existing.values() if row.id not in keep),
                     key=lambda row: row.position)
    for n, row in enumerate(retired):
        # Pushed past the live range so a retired field never shares a position with a kept one.
        row.active = False
        row.position = 1000 + n
    db.flush()


def create(db: Session, property_id: str, actor_id: str, data: LogTemplateIn) -> LogTemplate:
    name = _name(data.name)
    audience = _clean_audience(db, property_id, data.audience)
    position = db.scalar(select(func.count()).select_from(LogTemplate)
                         .where(LogTemplate.property_id == property_id))
    t = LogTemplate(property_id=property_id, name=name, shift=data.shift, active=data.active,
                    position=position, created_by_user_id=actor_id)
    db.add(t)
    db.flush()
    _sync_fields(db, t, data.fields)
    _replace_audience(db, t, audience)
    audit.record(db, property_id, actor_id, "log_template.created", "log_template", t.id,
                 after={"name": t.name})
    return t


def patch(db: Session, property_id: str, actor_id: str, template_id: str,
          data: LogTemplatePatch) -> LogTemplate:
    t = get(db, property_id, template_id)
    provided = data.model_dump(exclude_unset=True)
    if "name" in provided:
        t.name = _name(data.name or "")
    if "shift" in provided:
        t.shift = data.shift
    if "active" in provided and data.active is not None:
        t.active = data.active
    db.flush()
    if data.fields is not None:
        _sync_fields(db, t, data.fields)
    if data.audience is not None:
        _replace_audience(db, t, _clean_audience(db, property_id, data.audience))
    audit.record(db, property_id, actor_id, "log_template.updated", "log_template", t.id,
                 after={"fields": sorted(provided)})
    return t


# ---- posting with a template (spec §2.2, §2.3) -------------------------------------------------

MAX_SHORT_TEXT = 200
# log_entry_field_value.number_value is Numeric(10, 2): anything at or past 10**8 overflows it,
# which PostgreSQL refuses with a 500 and SQLite silently accepts. Refuse it here as a 400.
NUMBER_LIMIT = 100_000_000
NUMERIC_TYPES = {LogFieldType.integer, LogFieldType.decimal, LogFieldType.percent}


def _coerce(field_type: LogFieldType, raw: object) -> tuple[str | None, float | None, str | None]:
    """(text_value, number_value, failure reason). Both values None = unanswered."""
    if raw is None:
        return None, None, None
    if field_type not in NUMERIC_TYPES:
        text = str(raw).strip()
        if not text:
            return None, None, None
        limit = MAX_SHORT_TEXT if field_type == LogFieldType.short_text else MAX_BODY
        return (None, None, "too_long") if len(text) > limit else (text, None, None)
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None, None, None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None, None, "not_a_number"
    if not math.isfinite(number):  # float("nan") and float("inf") both parse
        return None, None, "not_a_number"
    if field_type == LogFieldType.integer and not number.is_integer():
        return None, None, "not_whole"
    if field_type == LogFieldType.percent and not 0 <= number <= 100:
        return None, None, "out_of_range"
    number = round(number, 2)  # round before the limit check: a value that only overflows
    if abs(number) >= NUMBER_LIMIT:  # after rounding (e.g. 99999999.996) must still be refused
        return None, None, "out_of_range"
    return None, number, None


def check_values(db: Session, template: LogTemplate,
                 values: list[LogFieldValueIn]) -> list[LogEntryFieldValue]:
    """Validate a post's answers against the template's active fields. Returns one unsaved value
    row per answered field, in field order, with the label and type snapshotted; the caller sets
    `log_entry_id` once the entry exists. Every failure is collected into one 400 whose details
    map each field id to its reason."""
    fields = active_fields(db, template.id)
    by_id = {f.id: f for f in fields}
    errors: dict[str, str] = {}
    given: dict[str, object] = {}
    for v in values:
        if v.field_id in given:
            errors[v.field_id] = "duplicate"
            continue
        given[v.field_id] = v.value
        if v.field_id not in by_id:
            errors[v.field_id] = "unknown_field"  # another template's, or soft-deleted
    rows: list[LogEntryFieldValue] = []
    for position, f in enumerate(fields):
        if f.id in errors:
            continue
        text, number, reason = _coerce(f.field_type, given.get(f.id))
        if reason:
            errors[f.id] = reason
        elif text is None and number is None:
            if f.required:
                errors[f.id] = "required"
        else:
            rows.append(LogEntryFieldValue(property_id=template.property_id, field_id=f.id,
                                           position=position, label=f.label,
                                           field_type=f.field_type, text_value=text,
                                           number_value=number))
    if errors:
        raise ValidationFailed("Some template fields need attention", details=errors)
    return rows


def format_value(field_type: LogFieldType, text_value: str | None,
                 number_value: float | None) -> str:
    if number_value is None:
        return text_value or ""
    shown = f"{number_value:.2f}".rstrip("0").rstrip(".")
    return f"{shown}%" if field_type == LogFieldType.percent else shown


def summary(values: list) -> str:
    """The generated half of a templated post's body: one `Label: value` line per answered
    field in position order. Duck-typed over value rows (label, field_type, text_value,
    number_value), so the read side rebuilds exactly the text the write side stored."""
    return "\n".join(f"{v.label}: {format_value(v.field_type, v.text_value, v.number_value)}"
                     for v in values)


def notes_of(body: str, values: list) -> str | None:
    """The author's notes: the body minus the generated summary and the blank line after it."""
    head = summary(values)
    rest = body[len(head):] if head and body.startswith(head) else body
    return rest.removeprefix("\n\n").strip() or None


# ---- the two lists (spec §3.2) --------------------------------------------------------------


def list_admin(db: Session, property_id: str) -> list[LogTemplateOut]:
    """Every template, inactive included, for Admin → Log templates."""
    rows = db.scalars(select(LogTemplate).where(LogTemplate.property_id == property_id)
                      .order_by(LogTemplate.position, LogTemplate.name, LogTemplate.id)).all()
    return _outs(db, property_id, list(rows))


def list_usable(db: Session, property_id: str, user_id: str) -> list[LogTemplateOut]:
    """The composer's picker: active templates the caller may post with, the current shift's
    first, then untagged and other shifts, each group by position then name."""
    rows = list(db.scalars(select(LogTemplate).where(LogTemplate.property_id == property_id,
                                                     LogTemplate.active.is_(True))).all())
    audiences = _audiences(db, [t.id for t in rows])
    membership = _membership(db, property_id, user_id)
    usable = [t for t in rows if _allowed(membership, audiences[t.id])]
    _, current = shifts.current_shift(db.get(Property, property_id), clock.now())
    usable.sort(key=lambda t: (t.shift != current, t.position, t.name, t.id))
    return _outs(db, property_id, usable)
