"""Maintainable-unit inventory (spec §3.1, §5.1, §5.4)."""
from __future__ import annotations

import csv
import io
from enum import StrEnum
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain import audit
from app.domain._patch import patch_changes
from app.errors import AppError, Conflict, NotFound
from app.models import MaintainableUnit
from app.schemas.enums import LocationType, PmUnitKind, PmUnitSource
from app.schemas.pm import (
    MAX_IMPORT_ROWS,
    UnitImportError,
    UnitImportOut,
    UnitIn,
    UnitListQuery,
    UnitOut,
    UnitPatch,
)


class ImportRejected(AppError):
    """422 whose `details` is the whole UnitImportOut report (spec §5.4). It rides in the
    standard error envelope because the web client's ApiError only reads `body.error` — a
    bare 422 payload would reach the form as "Request failed (422)" with the row list lost.
    Raised before any row is written."""

    status = 422
    code = "IMPORT_REJECTED"


# Where a work order raised from a unit is located (spec §4.1).
LOCATION_FOR_KIND: dict[PmUnitKind, LocationType] = {
    PmUnitKind.guest_room: LocationType.room,
    PmUnitKind.common_area: LocationType.public_area,
    PmUnitKind.equipment: LocationType.equipment,
}

IMPORT_COLUMNS = ("code", "kind", "name", "floor", "room_type", "external_id")
_LIMITS = {"code": 40, "name": 200, "room_type": 20, "external_id": 100}


def natural_key(code: str) -> tuple[int, int, str]:
    """Room numbers sort numerically (99 before 205 before 1001); everything else after them,
    alphabetically."""
    return (0, int(code), "") if code.isdigit() else (1, 0, code.lower())


def get(db: Session, property_id: str, unit_id: str) -> MaintainableUnit:
    unit = db.scalar(select(MaintainableUnit).where(MaintainableUnit.id == unit_id,
                                                    MaintainableUnit.property_id == property_id))
    if unit is None:
        raise NotFound("Unit not found")
    return unit


def to_out(unit: MaintainableUnit) -> UnitOut:
    return UnitOut.model_validate(unit)


def list_units(db: Session, property_id: str, query: UnitListQuery) -> list[UnitOut]:
    stmt = select(MaintainableUnit).where(MaintainableUnit.property_id == property_id)
    if query.kind:
        stmt = stmt.where(MaintainableUnit.kind == query.kind)
    if query.active is not None:
        stmt = stmt.where(MaintainableUnit.active.is_(query.active))
    if query.q and query.q.strip():
        needle = f"%{query.q.strip()}%"
        stmt = stmt.where(or_(MaintainableUnit.code.ilike(needle),
                              MaintainableUnit.name.ilike(needle)))
    rows = list(db.scalars(stmt).all())
    rows.sort(key=lambda u: (u.kind.value, natural_key(u.code)))
    return [to_out(u) for u in rows]


def _assert_code_free(db: Session, property_id: str, code: str,
                      exclude_id: str | None = None) -> None:
    stmt = select(MaintainableUnit.id).where(MaintainableUnit.property_id == property_id,
                                             MaintainableUnit.code == code)
    if exclude_id:
        stmt = stmt.where(MaintainableUnit.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"A unit with code {code} already exists", details={"code": "duplicate"})


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, StrEnum) else value


def create(db: Session, property_id: str, actor_user_id: str, data: UnitIn) -> MaintainableUnit:
    code = data.code.strip()
    _assert_code_free(db, property_id, code)
    unit = MaintainableUnit(property_id=property_id, kind=data.kind, code=code,
                            name=data.name.strip(), floor=data.floor, room_type=data.room_type,
                            external_id=data.external_id, notes=data.notes,
                            source=PmUnitSource.manual)
    db.add(unit)
    db.flush()
    audit.record(db, property_id, actor_user_id, "maintainable_unit.created",
                 "maintainable_unit", unit.id, after={"code": unit.code, "kind": unit.kind.value})
    return unit


def patch(db: Session, property_id: str, actor_user_id: str, unit_id: str,
          data: UnitPatch) -> MaintainableUnit:
    unit = get(db, property_id, unit_id)
    changes = patch_changes(MaintainableUnit, data)
    if "code" in changes:
        changes["code"] = changes["code"].strip()
        _assert_code_free(db, property_id, changes["code"], exclude_id=unit.id)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    before = {k: _plain(getattr(unit, k)) for k in changes}
    for key, value in changes.items():
        setattr(unit, key, value)
    db.flush()
    audit.record(db, property_id, actor_user_id, "maintainable_unit.updated",
                 "maintainable_unit", unit.id, before=before,
                 after={k: _plain(v) for k, v in changes.items()})
    return unit


def _rejected(errors: list[UnitImportError]) -> ImportRejected:
    report = UnitImportOut(created=0, updated=0, errors=errors)
    return ImportRejected("Import rejected — fix the listed rows and try again",
                          details=report.model_dump(mode="json", by_alias=True))


def import_csv(db: Session, property_id: str, actor_user_id: str, text: str) -> UnitImportOut:
    """Validate every row before writing any (spec §5.4). Rows upsert by (property, code); an
    updated row's `source` becomes `csv`. Any error → nothing written, ImportRejected raised
    with every error listed."""
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    if header != list(IMPORT_COLUMNS):
        raise _rejected([UnitImportError(
            line=1, field="header",
            message=f"Header must be exactly: {','.join(IMPORT_COLUMNS)}")])

    errors: list[UnitImportError] = []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def error(line: int, field: str, message: str) -> None:
        errors.append(UnitImportError(line=line, field=field, message=message))

    # Line 1 is the header, so the first data row is line 2.
    for line, raw in enumerate(reader, start=2):
        if line - 1 > MAX_IMPORT_ROWS:
            error(line, "file", f"At most {MAX_IMPORT_ROWS} rows per import")
            break
        row = {k: (v or "").strip() for k, v in raw.items() if k is not None}
        if not row["code"]:
            error(line, "code", "required")
            continue
        if row["code"] in seen:
            error(line, "code", f"duplicate code {row['code']} in this file")
            continue
        seen.add(row["code"])
        try:
            kind = PmUnitKind(row["kind"])
        except ValueError:
            error(line, "kind", "must be one of " + ", ".join(k.value for k in PmUnitKind))
            continue
        if not row["name"]:
            error(line, "name", "required")
            continue
        floor: int | None = None
        if row["floor"]:
            try:
                floor = int(row["floor"])
            except ValueError:
                error(line, "floor", "must be a whole number")
                continue
        too_long = [f for f, limit in _LIMITS.items() if len(row[f]) > limit]
        if too_long:
            error(line, too_long[0], f"longer than {_LIMITS[too_long[0]]} characters")
            continue
        rows.append({"code": row["code"], "kind": kind, "name": row["name"], "floor": floor,
                     "room_type": row["room_type"] or None,
                     "external_id": row["external_id"] or None})

    if errors:
        raise _rejected(errors)

    existing = {u.code: u for u in db.scalars(select(MaintainableUnit).where(
        MaintainableUnit.property_id == property_id)).all()}
    created = updated = 0
    for row in rows:
        unit = existing.get(row["code"])
        if unit is None:
            db.add(MaintainableUnit(property_id=property_id, source=PmUnitSource.csv, **row))
            created += 1
        else:
            unit.kind, unit.name, unit.floor = row["kind"], row["name"], row["floor"]
            unit.room_type = row["room_type"]
            unit.external_id = row["external_id"] or unit.external_id
            unit.source = PmUnitSource.csv
            updated += 1
    db.flush()
    audit.record(db, property_id, actor_user_id, "maintainable_unit.imported",
                 "maintainable_unit", None, after={"created": created, "updated": updated})
    return UnitImportOut(created=created, updated=updated, errors=[])
