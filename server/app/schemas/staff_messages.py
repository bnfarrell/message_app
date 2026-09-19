from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import Role, StaffConversationKind

MAX_PARTICIPANTS_PER_REQUEST = 100  # generous for a hotel; bounds the per-id _assert_member SELECTs


class CreateStaffConversationRequest(CamelModel):
    """POST /staff-conversations. `kind` picks which of the other fields apply; validated
    together in app.domain.staff_messages.create_conversation rather than as two separate
    Pydantic models, so the route stays a single endpoint (spec §3)."""

    kind: Literal[StaffConversationKind.dm, StaffConversationKind.group]
    user_id: str | None = None          # required, kind=dm
    name: str | None = Field(default=None, min_length=1, max_length=100)  # required, kind=group
    # required, kind=group
    user_ids: list[str] | None = Field(default=None, max_length=MAX_PARTICIPANTS_PER_REQUEST)


class GroupPatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = None


class AddParticipantsRequest(CamelModel):
    user_ids: list[str] = Field(min_length=1, max_length=MAX_PARTICIPANTS_PER_REQUEST)


class SendStaffMessageRequest(CamelModel):
    """The non-file half of the multipart body; a `photo` file part arrives alongside it,
    exactly like WorkOrderPhotoUpload."""

    body: str | None = Field(default=None, max_length=4000)


class StaffParticipantOut(CamelModel):
    user_id: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    role: Role
    department_id: str | None = None


class StaffMessageOut(CamelModel):
    id: str
    conversation_id: str
    author_user_id: str
    author_name: str
    body: str | None = None
    photo_url: str | None = None
    created_at: datetime


class StaffConversationOut(CamelModel):
    id: str
    kind: StaffConversationKind
    name: str | None = None
    avatar_url: str | None = None
    display_name: str
    other_user_id: str | None = None   # set only for kind=dm
    participants: list[StaffParticipantOut]
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
    unread: bool
    created_at: datetime
    updated_at: datetime


class StaffConversationDetail(StaffConversationOut):
    messages: list[StaffMessageOut]


class StaffDirectoryEntryOut(CamelModel):
    user_id: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    role: Role
    department_id: str | None = None
    department_name: str | None = None
