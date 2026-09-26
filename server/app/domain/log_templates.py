"""Hotel log post templates (log templates spec §2, §3).

Fields sync replace-by-list with soft deletes, like checklist items, but through their own rules
rather than app.domain.typed_items: the field types are not PM's item types, and there are no
bounds or units. A saved field's type never changes — value rows already posted against it would
mean something else.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import audit
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import (
    Department,
    LogEntry,
    LogTemplate,
    LogTemplateAudience,
    LogTemplateField,
    PropertyMembership,
)
from app.schemas.enums import MentionTargetType, Role
from app.schemas.log import (
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
