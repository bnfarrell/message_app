from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.domain._patch import patch_changes
from app.domain.guests import normalize_phone
from app.errors import NotFound, ValidationFailed
from app.models import Property
from app.schemas.properties import PropertySettingsOut, PropertySettingsPatch

# Stored E.164: app/channels/inbound.py routes an inbound SMS by matching
# `Property.sms_number == guests.normalize_phone(to_number)`, so a settings edit that saved a
# prettified number would silently stop inbound routing for the property.
_PHONE_FIELDS = ("phone", "sms_number")

# The three live keys inside the untyped `Property.settings` blob, with the defaults their
# readers already apply: domain/conversations.py `_setting` (sla_minutes, auto_resolve_hours) and
# channels/inbound.py (help_text, the guest-visible automatic reply to HELP). The blob itself
# stays off the API; these are exposed as typed, validated fields instead.
_BAG_DEFAULTS: dict[str, object] = {"sla_minutes": 15, "auto_resolve_hours": 4, "help_text": None}
_BAG_REQUIRED = ("sla_minutes", "auto_resolve_hours")  # `_setting` does int(...); None would 500


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


def _out(p: Property) -> PropertySettingsOut:
    bag = p.settings or {}
    return PropertySettingsOut(
        id=p.id, name=p.name, code=p.code, timezone=p.timezone, address=p.address, phone=p.phone,
        sms_number=p.sms_number, brand=p.brand, currency=p.currency, logo_url=p.logo_url,
        primary_color=p.primary_color,
        sla_minutes=int(bag.get("sla_minutes", _BAG_DEFAULTS["sla_minutes"])),
        auto_resolve_hours=int(bag.get("auto_resolve_hours", _BAG_DEFAULTS["auto_resolve_hours"])),
        help_text=bag.get("help_text"),
    )


def settings(db: Session, property_id: str) -> PropertySettingsOut:
    return _out(get(db, property_id))


def update_settings(db: Session, property_id: str,
                    data: PropertySettingsPatch) -> PropertySettingsOut:
    p = get(db, property_id)
    changes = patch_changes(Property, data, required=_BAG_REQUIRED)

    # `Property.settings` is a plain JSON column with no MutableDict, so mutating the dict in
    # place would never be flushed: the whole value has to be reassigned.
    bag_changes = {k: changes.pop(k) for k in list(changes) if k in _BAG_DEFAULTS}
    if bag_changes:
        p.settings = {**(p.settings or {}), **bag_changes}

    for k, v in changes.items():
        if v is not None:
            if k in _PHONE_FIELDS:
                v = normalize_phone(v)
            elif k == "timezone":
                v = normalize_timezone(v)
            elif k == "currency":
                v = v.upper()
        setattr(p, k, v)
    db.flush()
    return _out(p)
