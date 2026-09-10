from datetime import datetime

from app.schemas.common import CamelModel


class NotificationOut(CamelModel):
    id: str
    type: str
    title: str
    body: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    read_at: datetime | None = None
    created_at: datetime


class UnreadCount(CamelModel):
    count: int
