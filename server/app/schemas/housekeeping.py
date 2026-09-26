"""Housekeeping wire models (spec §4). Prefixed `Hk`: the exported JSON schema is flat and PM
already owns InspectRequest / InspectionRowOut."""
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import (
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    RoomEventType,
)


class HkAssignmentOut(CamelModel):
    id: str
    room_id: str
    housekeeper_user_id: str
    housekeeper_name: str | None = None
    shift_date: date
    sequence: int
    type: HkServiceType
    status: HkAssignmentStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    inspected_by_name: str | None = None
    inspected_at: datetime | None = None
    inspection_note: str | None = None
    fail_count: int


class HkRoomOut(CamelModel):
    id: str
    unit_id: str
    code: str
    floor: int | None = None
    room_type: str | None = None
    hk_status: HkStatus
    service_type: HkServiceType | None = None
    rush: bool
    occupancy: HkOccupancy
    guest_name: str | None = None
    departure_date: date | None = None
    status_changed_at: datetime
    last_cleaned_at: datetime | None = None
    last_inspected_at: datetime | None = None
    notes: str | None = None
    assignment: HkAssignmentOut | None = None


class HkSummaryOut(CamelModel):
    dirty: int
    in_progress: int
    awaiting_inspection: int
    inspected: int
    out_of_order: int  # out of order + out of service


class HkHousekeeperOut(CamelModel):
    user_id: str
    name: str
    assigned: int
    done: int


class HkBoardOut(CamelModel):
    rooms: list[HkRoomOut]
    summary: HkSummaryOut
    housekeepers: list[HkHousekeeperOut]


class HkPhotoOut(CamelModel):
    id: str
    content_type: str
    byte_size: int
    url: str
    created_at: datetime


class HkEventOut(CamelModel):
    id: str
    type: RoomEventType
    from_value: str | None = None
    to_value: str | None = None
    comment: str | None = None
    user_name: str | None = None
    created_at: datetime


class HkRoomDetailOut(CamelModel):
    room: HkRoomOut
    events: list[HkEventOut]
    photos: list[HkPhotoOut]


class HkInspectionRowOut(CamelModel):
    room: HkRoomOut
    photos: list[HkPhotoOut]


class HkMarkDirtyRequest(CamelModel):
    note: str | None = Field(default=None, max_length=2000)


class HkStatusRequest(CamelModel):
    status: Literal["out_of_order", "out_of_service", "dirty"]
    note: str | None = Field(default=None, max_length=2000)


class HkAssignRequest(CamelModel):
    room_ids: list[str] = Field(min_length=1, max_length=500)
    housekeeper_user_id: str


class HkReorderRequest(CamelModel):
    housekeeper_user_id: str
    assignment_ids: list[str] = Field(min_length=1, max_length=500)


class HkInspectRequest(CamelModel):
    result: Literal["pass", "fail"]
    note: str | None = Field(default=None, max_length=2000)
