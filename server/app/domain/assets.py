from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound
from app.models import DigitalAsset
from app.schemas.content import AssetIn, AssetOut, AssetPatch

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o/1/l/i
MAX_SHORT_CODE_ATTEMPTS = 20


def new_short_code(db: Session) -> str:
    for _ in range(MAX_SHORT_CODE_ATTEMPTS):
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not db.scalar(select(DigitalAsset.id).where(DigitalAsset.short_code == code)):
            return code
    raise Conflict(f"Could not generate a unique short code after {MAX_SHORT_CODE_ATTEMPTS} tries")


def list(db: Session, property_id: str, include_inactive: bool = False) -> list[AssetOut]:
    stmt = select(DigitalAsset).where(DigitalAsset.property_id == property_id)
    if not include_inactive:
        stmt = stmt.where(DigitalAsset.active.is_(True))
    return [AssetOut.model_validate(a) for a in db.scalars(stmt.order_by(DigitalAsset.name)).all()]


def get(db: Session, property_id: str, asset_id: str) -> DigitalAsset:
    a = db.scalar(select(DigitalAsset).where(DigitalAsset.id == asset_id, DigitalAsset.property_id == property_id))
    if a is None:
        raise NotFound("Asset not found")
    return a


def get_by_short_code(db: Session, short_code: str) -> DigitalAsset | None:
    return db.scalar(select(DigitalAsset).where(DigitalAsset.short_code == short_code, DigitalAsset.active.is_(True)))


def create(db: Session, property_id: str, data: AssetIn) -> DigitalAsset:
    # SELECT-then-INSERT on short_code races under concurrent creates; the DB's unique
    # constraint is the real guard, so catch its violation and retry with a fresh code rather
    # than let a collision surface as an unhandled IntegrityError (see Task 16 review round 1).
    for _ in range(MAX_SHORT_CODE_ATTEMPTS):
        a = DigitalAsset(property_id=property_id, short_code=new_short_code(db),
                         **data.model_dump())
        try:
            with db.begin_nested():
                db.add(a)
                db.flush()
        except IntegrityError:
            continue
        return a
    raise Conflict(f"Could not generate a unique short code after {MAX_SHORT_CODE_ATTEMPTS} tries")


def update(db: Session, property_id: str, asset_id: str, data: AssetPatch) -> DigitalAsset:
    a = get(db, property_id, asset_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.flush()
    return a


def delete(db: Session, property_id: str, asset_id: str) -> None:
    a = get(db, property_id, asset_id)
    a.active = False  # soft: messages already sent still reference the id; the short link stops resolving
