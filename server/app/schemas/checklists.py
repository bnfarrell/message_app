"""Shift-checklist wire models (checklists spec §4). Items, answers and photos reuse PM's models
so PM's ChecklistItem component renders checklist rows unchanged."""
from datetime import date, datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import ChecklistKind, ChecklistSchedule, ChecklistStatus, Shift
from app.schemas.pm import RunAnswerOut, RunPhotoOut, TemplateItemIn, TemplateItemOut

MAX_CATEGORIES = 30


class ChecklistItemIn(TemplateItemIn):
    """PM's item plus the category it sits under, named by a `key` from the same request's
    `categories` (checklist structure spec §3.2). PM's own TemplateItemIn is unchanged."""

    category_key: str | None = Field(default=None, min_length=1, max_length=64)


class ChecklistCategoryIn(CamelModel):
    """`key` is the client's handle for this category within one request; `id` names a saved
    category to update in place. A saved category missing from the list is soft-deleted."""

    key: str = Field(min_length=1, max_length=64)
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)


class ChecklistItemOut(TemplateItemOut):
    category_id: str | None = None


class ChecklistCategoryOut(CamelModel):
    id: str
    name: str
    position: int


class ChecklistTemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    department_id: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool = True
    kind: ChecklistKind = ChecklistKind.normal
    categories: list[ChecklistCategoryIn] = Field(default_factory=list,
                                                  max_length=MAX_CATEGORIES)
    items: list[ChecklistItemIn] = Field(min_length=1, max_length=100)


class ChecklistTemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    department_id: str | None = None
    schedule: ChecklistSchedule | None = None
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool | None = None
    kind: ChecklistKind | None = None
    categories: list[ChecklistCategoryIn] | None = Field(default=None, max_length=MAX_CATEGORIES)
    items: list[ChecklistItemIn] | None = Field(default=None, min_length=1, max_length=100)


class ChecklistTemplateOut(CamelModel):
    id: str
    name: str
    department_id: str
    department_name: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = None
    active: bool
    kind: ChecklistKind
    categories: list[ChecklistCategoryOut]
    items: list[ChecklistItemOut]


class ChecklistCategoryProgressOut(ChecklistCategoryOut):
    """A category heading on the checklist page: `done / total` over its items."""

    done: int
    total: int


class ChecklistInstanceRowOut(CamelModel):
    id: str
    template_id: str
    template_name: str
    department_id: str
    department_name: str
    due_date: date
    shift: Shift
    on_demand: bool
    status: ChecklistStatus
    kind: ChecklistKind
    assigned_user_id: str | None = None
    assigned_name: str | None = None
    completed_by_name: str | None = None
    done: int
    total: int
    out_of_range_count: int


class ChecklistInstanceOut(ChecklistInstanceRowOut):
    started_by_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    comment: str | None = None
    categories: list[ChecklistCategoryProgressOut]
    items: list[ChecklistItemOut]
    answers: list[RunAnswerOut]
    photos: list[RunPhotoOut]
    missing_required: list[str]


class ChecklistAssignRequest(CamelModel):
    user_id: str | None = None


class ChecklistCommentPatch(CamelModel):
    comment: str | None = Field(default=None, max_length=4000)


class ChecklistInstanceQuery(CamelModel):
    # `day`, not `date`: a field named after its own type shadows it inside the class body.
    day: date | None = None
    department_id: str | None = None
    status: ChecklistStatus | None = None


class ChecklistMissedQuery(CamelModel):
    days: int = Field(default=7, ge=1, le=90)
