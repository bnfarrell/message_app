import json
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import CamelModel
from app.schemas.enums import LogFieldType, MentionTargetType, Shift

MAX_BODY = 4000
MAX_MENTIONS = 100          # a hotel-sized bound on the per-id validation SELECTs
FEED_PAGE_SIZE = 50
MAX_TEMPLATE_FIELDS = 50


class MentionRef(CamelModel):
    """One @mention or one member of an acknowledgement audience."""

    type: MentionTargetType
    id: str


class LogFieldValueIn(CamelModel):
    """One answer on a templated post. A JSON number or a numeric string (the multipart path
    sends strings); the domain validates it against the field's type (log templates spec §2.3)."""

    field_id: str
    value: str | float | int | None = None


class CreateLogEntryRequest(CamelModel):
    """The non-file half of the body; a `photo` file part may arrive alongside it, exactly
    like SendStaffMessageRequest. With `template_id`, `body` is the author's optional notes and
    the domain generates the stored body (log templates spec §2.2)."""

    body: str = Field(default="", max_length=MAX_BODY)
    department_id: str | None = None
    mentions: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)
    requires_ack: bool = False
    ack_audience: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)
    linked_work_order_id: str | None = None
    linked_conversation_id: str | None = None
    template_id: str | None = None
    field_values: list[LogFieldValueIn] = Field(default_factory=list,
                                                max_length=MAX_TEMPLATE_FIELDS)

    @model_validator(mode="before")
    @classmethod
    def _parse_multipart_lists(cls, data: Any) -> Any:
        """`parse_body` falls back to `request.form.to_dict()` for multipart requests, which
        yields strings for every field. A JSON body already gives these as lists, so only
        the string case (the multipart path) needs decoding."""
        if not isinstance(data, dict):
            return data
        for field in ("mentions", "ackAudience", "fieldValues"):
            value = data.get(field)
            if isinstance(value, str):
                data[field] = json.loads(value)
        return data


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


class LogTemplateRef(CamelModel):
    id: str
    name: str


class LogFieldValueOut(CamelModel):
    field_id: str
    label: str
    field_type: LogFieldType
    text_value: str | None = None
    number_value: float | None = None


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
    template: LogTemplateRef | None = None
    field_values: list[LogFieldValueOut] = Field(default_factory=list)
    # The author's notes on a templated post — the body minus its generated field summary — so
    # the card can show the values as a table without repeating them (spec §4.2). None on a
    # free-form post, whose `body` is already the whole text.
    notes: str | None = None


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


class LogTemplateFieldIn(CamelModel):
    """`id` set = update that field in place; omitted = a new field. A saved field missing from
    the list is soft-deleted, and its type never changes (log templates spec §2.1)."""

    id: str | None = None
    label: str = Field(min_length=1, max_length=200)
    field_type: LogFieldType
    required: bool = True


class LogTemplateFieldOut(CamelModel):
    id: str
    position: int
    label: str
    field_type: LogFieldType
    required: bool
    active: bool


class LogTemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    shift: Shift | None = None
    active: bool = True
    fields: list[LogTemplateFieldIn] = Field(min_length=1, max_length=MAX_TEMPLATE_FIELDS)
    audience: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)


class LogTemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    shift: Shift | None = None
    active: bool | None = None
    fields: list[LogTemplateFieldIn] | None = Field(default=None, min_length=1,
                                                    max_length=MAX_TEMPLATE_FIELDS)
    audience: list[MentionRef] | None = Field(default=None, max_length=MAX_MENTIONS)


class LogTemplateOut(CamelModel):
    id: str
    name: str
    shift: Shift | None = None
    active: bool
    position: int
    fields: list[LogTemplateFieldOut]
    audience: list[MentionRef]
    used_count: int
