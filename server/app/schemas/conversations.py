from datetime import date, datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import (
    AuthorType,
    Channel,
    ConversationStatus,
    DeliveryStatus,
    Direction,
    DraftPromptStatus,
    Priority,
    SmsConsentStatus,
    StayStatus,
    WorkOrderStatus,
    WorkOrderType,
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


class NoteOut(CamelModel):
    id: str
    author_user_id: str
    author_name: str
    body: str
    mentions: list[str]
    created_at: datetime


class WorkOrderBrief(CamelModel):
    id: str
    title: str
    status: WorkOrderStatus
    priority: Priority
    type: WorkOrderType
    department_id: str | None = None
    assigned_user_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    guest_notified_at: datetime | None = None


class DraftPromptOut(CamelModel):
    id: str
    work_order_id: str
    work_order_title: str
    body: str
    status: DraftPromptStatus
    created_at: datetime


class ConversationDetail(CamelModel):
    id: str
    status: ConversationStatus
    guest: GuestOut
    stay: StayOut | None = None
    assigned_user_id: str | None = None
    assigned_department_id: str | None = None
    channel_primary: Channel
    last_guest_message_at: datetime | None = None
    last_staff_message_at: datetime | None = None
    first_response_seconds: int | None = None
    sla_due_at: datetime | None = None
    snoozed_until: datetime | None = None
    resolution_category_id: str | None = None
    archived_at: datetime | None = None
    messages: list[MessageOut]
    notes: list[NoteOut]
    work_orders: list[WorkOrderBrief]
    draft_prompts: list[DraftPromptOut]


class GuestThreadMessage(CamelModel):
    """What a guest could ever see. Deliberately has no field that could carry an internal note."""

    id: str
    direction: Direction
    body: str
    sent_at: datetime | None = None
    delivery_status: DeliveryStatus


class GuestThread(CamelModel):
    phone: str
    property_name: str
    messages: list[GuestThreadMessage]


class ConversationPatch(CamelModel):
    assigned_user_id: str | None = None
    assigned_department_id: str | None = None
    status: ConversationStatus | None = None
    resolution_category_id: str | None = None
    snoozed_until: datetime | None = None
    clear_assignment: bool = False


class CreateNoteRequest(CamelModel):
    body: str = Field(min_length=1, max_length=4000)


class ListQuery(CamelModel):
    filter: str = "all"
    dept: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
