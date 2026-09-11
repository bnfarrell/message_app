"""TCPA consent (design.md §9.1). assert_can_send() is called from exactly one place:
messages.send()."""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from sqlalchemy.orm import Session

from app import clock
from app.domain import audit
from app.errors import ConsentError
from app.models import Guest
from app.schemas.enums import SmsConsentStatus

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
START_WORDS = {"start", "unstop", "yes"}
HELP_WORDS = {"help"}

Keyword = Literal["stop", "start", "help"]


def classify_keyword(body: str) -> Keyword | None:
    normalized = body.strip().lower().rstrip(" .,!?")
    if not normalized:
        return None
    if normalized in STOP_WORDS:
        return "stop"
    if normalized in START_WORDS:
        return "start"
    if normalized in HELP_WORDS:
        return "help"
    return None


def STOP_CONFIRMATION(property_name: str) -> str:
    return f"You're unsubscribed from {property_name} messages. Reply START to resume."


def _set(db: Session, guest: Guest, status: SmsConsentStatus, source: str) -> None:
    before = {"sms_consent_status": guest.sms_consent_status.value}
    guest.sms_consent_status = status
    guest.sms_consent_at = clock.now()
    guest.sms_consent_source = source
    db.flush()
    audit.record(db, guest.property_id, None, f"consent.{status.value}", "guest", guest.id,
                 before=before, after={"sms_consent_status": status.value, "source": source})


def opt_out(db: Session, guest: Guest, source: str) -> None:
    _set(db, guest, SmsConsentStatus.opted_out, source)


def opt_in(db: Session, guest: Guest, source: str) -> None:
    _set(db, guest, SmsConsentStatus.opted_in, source)


def assert_can_send(guest: Guest, *, allow_opt_out_confirmation: bool = False,
                    audit_write: Callable[[Session], None] | None = None) -> None:
    if guest.sms_consent_status == SmsConsentStatus.opted_out and not allow_opt_out_confirmation:
        raise ConsentError("Guest has opted out of SMS", audit_write=audit_write)
