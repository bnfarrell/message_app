from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import (
    LocationType,
    Priority,
    WorkOrderEventType,
    WorkOrderPhotoKind,
    WorkOrderStatus,
    WorkOrderType,
)


class CreateWorkOrder(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    type: WorkOrderType = WorkOrderType.maintenance
    priority: Priority = Priority.normal
    location_type: LocationType = LocationType.room
    location_ref: str | None = None
    department_id: str | None = None
    assigned_user_id: str | None = None
    due_at: datetime | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None


class WorkOrderPatch(CamelModel):
    status: WorkOrderStatus | None = None
    assigned_user_id: str | None = None
    department_id: str | None = None
    priority: Priority | None = None
    comment: str | None = Field(default=None, max_length=2000)
    clear_assignee: bool = False


class WorkOrderOut(CamelModel):
    id: str
    title: str
    description: str | None = None
    type: WorkOrderType
    priority: Priority
    status: WorkOrderStatus
    location_type: LocationType
    location_ref: str | None = None
    department_id: str | None = None
    assigned_user_id: str | None = None
    reported_by_user_id: str | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    due_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    verified_at: datetime | None = None
    guest_notified_at: datetime | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkOrderEventOut(CamelModel):
    id: str
    user_id: str | None = None
    user_name: str | None = None
    type: WorkOrderEventType
    from_value: str | None = None
    to_value: str | None = None
    comment: str | None = None
    created_at: datetime


class WorkOrderPhotoUpload(CamelModel):
    """The non-file half of the multipart body. The file itself arrives as the `photo` part."""

    kind: WorkOrderPhotoKind


class WorkOrderPhotoOut(CamelModel):
    id: str
    work_order_id: str
    kind: WorkOrderPhotoKind
    content_type: str
    byte_size: int
    uploaded_by_user_id: str | None = None
    uploaded_by_name: str | None = None
    # Ready to drop into an <img src>; the bytes are behind the same property gate as this record.
    url: str
    created_at: datetime


class WorkOrderDetail(WorkOrderOut):
    events: list[WorkOrderEventOut]
    photos: list[WorkOrderPhotoOut]
    guest_name: str | None = None
    room_number: str | None = None
    # Set on a scheduled-PM work order; the detail page links to the checklist (PM spec §7.7).
    pm_run_id: str | None = None


class WorkOrderPrefill(CamelModel):
    title: str
    description: str
    type: WorkOrderType
    priority: Priority
    location_type: LocationType
    location_ref: str | None = None
    department_id: str | None = None
    guest_name: str | None = None
    source_conversation_id: str
    source_message_id: str | None = None


class WorkOrderListQuery(CamelModel):
    status: str | None = None          # comma-separated
    type: WorkOrderType | None = None
    dept: str | None = None
    assignee: str | None = None
    mine: bool = False
    include_closed: bool = False
