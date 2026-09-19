from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import MentionTargetType, Shift

MAX_BODY = 4000
MAX_MENTIONS = 100          # a hotel-sized bound on the per-id validation SELECTs
FEED_PAGE_SIZE = 50


class MentionRef(CamelModel):
    """One @mention or one member of an acknowledgement audience."""

    type: MentionTargetType
    id: str


class CreateLogEntryRequest(CamelModel):
    """The non-file half of the body; a `photo` file part may arrive alongside it, exactly
    like SendStaffMessageRequest."""

    body: str = Field(min_length=1, max_length=MAX_BODY)
    department_id: str | None = None
    mentions: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)
    requires_ack: bool = False
    ack_audience: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)
    linked_work_order_id: str | None = None
    linked_conversation_id: str | None = None


class LogFeedQuery(CamelModel):
    shift: Shift | None = None
    department_id: str | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    mentioning_me: bool = False
    cursor: str | None = None


class LogMentionOut(CamelModel):
    type: MentionTargetType
    id: str
    display_name: str


class LogAckOut(CamelModel):
    user_id: str
    name: str
    acknowledged_at: datetime


class LogPersonOut(CamelModel):
    user_id: str
    name: str


class LogEntryOut(CamelModel):
    id: str
    created_at: datetime
    author_user_id: str
    author_name: str
    author_avatar_url: str | None = None
    department_id: str | None = None
    department_name: str | None = None
    shift: Shift
    body: str
    mentions: list[LogMentionOut] = Field(default_factory=list)
    pinned: bool
    pinned_by_user_id: str | None = None
    pinned_at: datetime | None = None
    requires_ack: bool
    ack_expected_count: int
    acks: list[LogAckOut] = Field(default_factory=list)
    outstanding: list[LogPersonOut] = Field(default_factory=list)
    acked_by_me: bool
    can_ack: bool
    photo_url: str | None = None
    linked_work_order_id: str | None = None
    linked_conversation_id: str | None = None


class LogFeedOut(CamelModel):
    pinned: list[LogEntryOut] = Field(default_factory=list)
    entries: list[LogEntryOut] = Field(default_factory=list)
    next_cursor: str | None = None


class LogMentionableOut(CamelModel):
    """One row of the composer's picker — a person or a department, one flat list."""

    type: MentionTargetType
    id: str
    display_name: str
    subtitle: str | None = None
