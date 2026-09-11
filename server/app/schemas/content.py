from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import AssetType


class QuickReplyIn(CamelModel):
    shortcut: str = Field(min_length=2, max_length=40, pattern=r"^/[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1600)
    category: str | None = None
    department_id: str | None = None
    locale: str = "en"
    active: bool = True


class QuickReplyPatch(CamelModel):
    shortcut: str | None = Field(default=None, pattern=r"^/[a-z0-9_-]+$")
    title: str | None = None
    body: str | None = None
    category: str | None = None
    department_id: str | None = None
    active: bool | None = None


class QuickReplyOut(CamelModel):
    id: str
    shortcut: str
    title: str
    body: str
    category: str | None = None
    department_id: str | None = None
    locale: str
    usage_count: int
    active: bool


class RenderRequest(CamelModel):
    conversation_id: str


class RenderedQuickReply(CamelModel):
    body: str
    segments: int
    characters: int


class AssetIn(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    category: str | None = None
    type: AssetType = AssetType.link
    url: str = Field(min_length=1, max_length=1000)
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool = True
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class AssetPatch(CamelModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    type: AssetType | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class AssetOut(CamelModel):
    id: str
    name: str
    description: str | None = None
    category: str | None = None
    type: AssetType
    url: str
    short_code: str
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    send_count: int


class CategoryIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: str | None = None
    active: bool = True


class CategoryPatch(CamelModel):
    name: str | None = None
    parent_id: str | None = None
    active: bool | None = None


class CategoryOut(CamelModel):
    id: str
    name: str
    parent_id: str | None = None
    active: bool
    children: list["CategoryOut"] = []
