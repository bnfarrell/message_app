from datetime import datetime
from typing import Any

from app.schemas.common import CamelModel
from app.schemas.enums import SmsConsentStatus


class SimGuest(CamelModel):
    property_id: str
    property_name: str
    property_sms_number: str | None = None
    guest_id: str
    name: str
    phone: str
    room_number: str | None = None
    in_house: bool
    sms_consent_status: SmsConsentStatus
    will_fail: bool


class SimEvent(CamelModel):
    type: str
    property_id: str
    at: datetime
    payload: dict[str, Any]
