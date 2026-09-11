from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.domain.guests import normalize_phone
from app.errors import NotFound, ValidationFailed
from app.models import Property
from app.schemas.properties import PropertySettingsOut, PropertySettingsPatch

# Stored E.164: app/channels/inbound.py routes an inbound SMS by matching
# `Property.sms_number == guests.normalize_phone(to_number)`, so a settings edit that saved a
# prettified number would silently stop inbound routing for the property.
_PHONE_FIELDS = ("phone", "sms_number")


def normalize_timezone(raw: str) -> str:
    """The zone is the intended basis for analytics bucketing, so a typo must be rejected rather
    than persisted. Validated here rather than in a Pydantic validator to match `normalize_phone`,
    the codebase's existing field-normalisation precedent."""
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValidationFailed("Invalid time zone", details={"timezone": raw}) from e
    return raw


def get(db: Session, property_id: str) -> Property:
    p = db.get(Property, property_id)
    if p is None:
        raise NotFound("Property not found")
    return p


def settings(db: Session, property_id: str) -> PropertySettingsOut:
    return PropertySettingsOut.model_validate(get(db, property_id))


def update_settings(db: Session, property_id: str,
                    data: PropertySettingsPatch) -> PropertySettingsOut:
    p = get(db, property_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            if k in _PHONE_FIELDS:
                v = normalize_phone(v)
            elif k == "timezone":
                v = normalize_timezone(v)
            elif k == "currency":
                v = v.upper()
        setattr(p, k, v)
    db.flush()
    return PropertySettingsOut.model_validate(p)
