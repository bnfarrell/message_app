from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ValidationFailed
from app.models import Guest

# The "+" branch below accepted any digit count, so "+" and "+1-" normalised to "+" and "+1" and
# saved cleanly. On Property.sms_number that is an outage: channels/inbound.py routes a guest's
# SMS by `Property.sms_number == normalize_phone(To)`, so one admin typo silently drops every
# inbound message for the property (ruling D83).
#
# The floor is deliberately 2 rather than a full E.164 length. This function also normalises SMS
# short codes, which are legitimate senders at 3-6 digits in the shortest national schemes, and
# guest numbers arriving from inbound webhooks. A floor tuned to a full subscriber number would
# reject that legitimate traffic — the same outage in the other direction. 2 is simultaneously the
# smallest floor that rejects both reported typos and comfortably below the shortest short code,
# so it cannot reject one.
MIN_SENDER_DIGITS = 2


def normalize_phone(raw: str) -> str:
    raw = raw.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        if len(digits) < MIN_SENDER_DIGITS:
            raise ValidationFailed("Invalid phone number", details={"phone": raw})
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    raise ValidationFailed("Invalid phone number", details={"phone": raw})


def find_by_phone(db: Session, property_id: str, phone: str) -> Guest | None:
    return db.scalar(select(Guest).where(Guest.property_id == property_id,
                                         Guest.phone_e164 == normalize_phone(phone)))


def find_or_create_by_phone(db: Session, property_id: str, phone: str) -> tuple[Guest, bool]:
    existing = find_by_phone(db, property_id, phone)
    if existing:
        return existing, False
    normalized = normalize_phone(phone)
    try:
        with db.begin_nested():
            g = Guest(property_id=property_id, phone_e164=normalized)
            db.add(g)
            db.flush()
    except IntegrityError:
        g = find_by_phone(db, property_id, normalized)
        return g, False
    return g, True


def get(db: Session, property_id: str, guest_id: str) -> Guest | None:
    return db.scalar(select(Guest).where(Guest.id == guest_id, Guest.property_id == property_id))
