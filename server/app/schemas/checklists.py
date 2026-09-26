"""Shift-checklist wire models (checklists spec §4). Items, answers and photos reuse PM's models
so PM's ChecklistItem component renders checklist rows unchanged."""
from datetime import date, datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import ChecklistSchedule, ChecklistStatus, Shift
from app.schemas.pm import RunAnswerOut, RunPhotoOut, TemplateItemIn, TemplateItemOut


class ChecklistTemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    department_id: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool = True
    items: list[TemplateItemIn] = Field(min_length=1, max_length=100)


class ChecklistTemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    department_id: str | None = None
    schedule: ChecklistSchedule | None = None
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool | None = None
    items: list[TemplateItemIn] | None = Field(default=None, min_length=1, max_length=100)


class ChecklistTemplateOut(CamelModel):
    id: str
    name: str
    department_id: str
    department_name: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = None
    active: bool
    items: list[TemplateItemOut]


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
    items: list[TemplateItemOut]
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
