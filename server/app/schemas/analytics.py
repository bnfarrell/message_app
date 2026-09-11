from datetime import datetime

from app.schemas.common import CamelModel


class HourBucket(CamelModel):
    hour: int
    count: int


class DayBucket(CamelModel):
    day: str
    count: int


class DepartmentBucket(CamelModel):
    department_id: str | None = None
    department_name: str
    closed: int
    mean_time_to_resolve_seconds: int | None = None


class ResponseBucket(CamelModel):
    label: str
    count: int
    share: float


class Overview(CamelModel):
    since: datetime
    until: datetime
    conversations: int
    inbound_messages: int
    outbound_messages: int
    first_response_p50_seconds: int | None = None
    first_response_p90_seconds: int | None = None
    sla_breaches: int
    sla_breach_rate: float
    work_orders_created: int
    work_orders_closed: int
    work_orders_from_conversations: int
    mean_time_to_resolve_seconds: int | None = None
    inbound_by_hour: list[HourBucket]
    inbound_by_day: list[DayBucket]
    first_response_distribution: list[ResponseBucket]
    work_orders_by_department: list[DepartmentBucket]


class AgentStats(CamelModel):
    user_id: str
    name: str
    conversations_handled: int
    messages_sent: int
    first_response_p50_seconds: int | None = None
    first_response_p90_seconds: int | None = None
    sla_breaches: int
    quick_reply_share: float | None = None
    work_orders_created: int
