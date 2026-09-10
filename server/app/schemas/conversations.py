from datetime import date, datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import (
    AuthorType,
    Channel,
    ConversationStatus,
    DeliveryStatus,
    Direction,
    SmsConsentStatus,
    StayStatus,
)


class MessageOut(CamelModel):
    id: str
    conversation_id: str
    direction: Direction
    author_type: AuthorType
    author_user_id: str | None = None
    channel: Channel
    body: str
    digital_asset_id: str | None = None
    delivery_status: DeliveryStatus
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    redacted: bool
    sent_at: datetime | None = None
    delivered_at: datetime | None = None


class GuestOut(CamelModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    phone_e164: str
    email: str | None = None
    loyalty_tier: str | None = None
    vip: bool
    sms_consent_status: SmsConsentStatus
    notes_summary: str | None = None


class StayOut(CamelModel):
    id: str
    room_number: str | None = None
    room_type: str | None = None
    status: StayStatus
    arrival_date: date
    departure_date: date
    adults: int
    children: int
    is_return_guest: bool
    stay_count: int


class ConversationSummary(CamelModel):
    id: str
    status: ConversationStatus
    guest: GuestOut
    room_number: str | None = None
    assigned_user_id: str | None = None
    assigned_department_id: str | None = None
    channel_primary: Channel
    last_guest_message_at: datetime | None = None
    last_staff_message_at: datetime | None = None
    last_message_preview: str | None = None
    sla_due_at: datetime | None = None
    unanswered: bool
    open_work_order_count: int
    snoozed_until: datetime | None = None


class SendMessageRequest(CamelModel):
    body: str = Field(min_length=1, max_length=1600)
    digital_asset_id: str | None = None
    draft_prompt_id: str | None = None
