"""Aggregations are computed in Python from narrow selects so they run identically on SQLite and
Postgres."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import (
    Conversation,
    Department,
    Message,
    Property,
    PropertyMembership,
    UserAccount,
    WorkOrder,
)
from app.schemas.analytics import (
    AgentStats,
    DayBucket,
    DepartmentBucket,
    HourBucket,
    Overview,
    ResponseBucket,
)
from app.schemas.enums import AuthorType, Direction, WorkOrderStatus

CLOSED = (WorkOrderStatus.complete, WorkOrderStatus.verified)
BUCKETS = [("< 2 min", 0, 120), ("2–5 min", 120, 300), ("5–15 min", 300, 900),
           ("15–30 min", 900, 1800), ("30+ min", 1800, 10**9)]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    k = max(1, math.ceil(p / 100 * len(xs)))
    return xs[k - 1]


def default_range(since: datetime | None, until: datetime | None) -> tuple[datetime, datetime]:
    until = until or clock.now()
    since = since or (until - timedelta(days=7))
    return since, until


def property_zone(db: Session, property_id: str) -> ZoneInfo:
    """The property's own IANA zone. domain.properties.normalize_timezone validates it on write."""
    return ZoneInfo(db.scalar(select(Property.timezone).where(Property.id == property_id))
                    or "UTC")


def local(at: datetime, zone: ZoneInfo) -> datetime:
    """Move a stored UTC instant into the property's wall clock.

    `sent_at` is conceptually UTC and app.db.UTCDateTime hands it back aware, but UTC is attached
    explicitly for a naive value rather than left to `astimezone()`, which would read the *server
    machine's* local zone instead — a wrong answer that only appears off a UTC host.
    """
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(zone)


def overview(db: Session, property_id: str, since: datetime | None = None,
            until: datetime | None = None) -> Overview:
    since, until = default_range(since, until)
    convs = db.scalars(select(Conversation).where(
        Conversation.property_id == property_id,
        Conversation.created_at >= since, Conversation.created_at < until)).all()
    msgs = db.execute(select(Message.direction, Message.sent_at, Message.author_type).where(
        Message.property_id == property_id, Message.sent_at >= since,
        Message.sent_at < until)).all()
    inbound = [m for m in msgs if m.direction == Direction.inbound]
    outbound = [m for m in msgs
               if m.direction == Direction.outbound and m.author_type == AuthorType.staff]
    frs = [c.first_response_seconds for c in convs if c.first_response_seconds is not None]
    breaches = sum(1 for c in convs if c.sla_breach_notified_at is not None)
    # Buckets are the property's local hours and days: a duty manager reading "busiest hour" or
    # a per-day chart means their own wall clock, and a 9pm New York message belongs to that day,
    # not to the next one it falls on in UTC. `since`/`until` above stay UTC instants — they
    # select which messages are in range, not which bucket one lands in, so converting them too
    # would double-apply the offset.
    zone = property_zone(db, property_id)
    local_inbound = [local(m.sent_at, zone) for m in inbound]
    by_hour = Counter(at.hour for at in local_inbound)
    by_day = Counter(at.date().isoformat() for at in local_inbound)
    dist = [ResponseBucket(label=label, count=sum(1 for v in frs if lo <= v < hi),
                           share=(sum(1 for v in frs if lo <= v < hi) / len(frs)) if frs else 0.0)
            for label, lo, hi in BUCKETS]
    wos_created = db.scalars(select(WorkOrder).where(
        WorkOrder.property_id == property_id,
        WorkOrder.created_at >= since, WorkOrder.created_at < until)).all()
    wos_closed = db.scalars(select(WorkOrder).where(
        WorkOrder.property_id == property_id, WorkOrder.status.in_(CLOSED),
        WorkOrder.completed_at >= since, WorkOrder.completed_at < until)).all()
    ttr = [(w.completed_at - w.created_at).total_seconds() for w in wos_closed if w.completed_at]
    dept_names = {d.id: d.name for d in db.scalars(
        select(Department).where(Department.property_id == property_id)).all()}
    per_dept: dict[str | None, list[float]] = defaultdict(list)
    for w in wos_closed:
        per_dept[w.department_id].append((w.completed_at - w.created_at).total_seconds())
    dept_rows = sorted(
        [DepartmentBucket(department_id=d, department_name=dept_names.get(d, "Unassigned"),
                          closed=len(v),
                          mean_time_to_resolve_seconds=int(sum(v) / len(v)) if v else None)
         for d, v in per_dept.items()],
        key=lambda r: -r.closed)
    return Overview(
        since=since, until=until, conversations=len(convs), inbound_messages=len(inbound),
        outbound_messages=len(outbound),
        first_response_p50_seconds=int(percentile(frs, 50)) if frs else None,
        first_response_p90_seconds=int(percentile(frs, 90)) if frs else None,
        sla_breaches=breaches, sla_breach_rate=(breaches / len(convs)) if convs else 0.0,
        work_orders_created=len(wos_created), work_orders_closed=len(wos_closed),
        work_orders_from_conversations=sum(1 for w in wos_created if w.source_conversation_id),
        mean_time_to_resolve_seconds=int(sum(ttr) / len(ttr)) if ttr else None,
        inbound_by_hour=[HourBucket(hour=h, count=by_hour.get(h, 0)) for h in range(24)],
        inbound_by_day=[DayBucket(day=d, count=n) for d, n in sorted(by_day.items())],
        first_response_distribution=dist, work_orders_by_department=dept_rows)


def agents(db: Session, property_id: str, since: datetime | None = None,
          until: datetime | None = None,
          only_user_id: str | None = None) -> list[AgentStats]:
    since, until = default_range(since, until)
    staff = db.execute(select(UserAccount, PropertyMembership)
                       .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
                       .where(PropertyMembership.property_id == property_id)).all()
    sent = db.execute(select(
        Message.author_user_id, Message.conversation_id, Message.sent_at).where(
        Message.property_id == property_id, Message.direction == Direction.outbound,
        Message.author_type == AuthorType.staff,
        Message.sent_at >= since, Message.sent_at < until)).all()
    first_reply: dict[str, tuple[datetime, str]] = {}
    for author, conv_id, at in sorted(sent, key=lambda r: r.sent_at):
        first_reply.setdefault(conv_id, (at, author))
    convs = {c.id: c for c in db.scalars(
        select(Conversation).where(Conversation.property_id == property_id)).all()}
    wos = Counter(w.reported_by_user_id for w in db.scalars(select(WorkOrder).where(
        WorkOrder.property_id == property_id,
        WorkOrder.created_at >= since, WorkOrder.created_at < until)).all())
    out = []
    for u, _m in staff:
        if only_user_id and u.id != only_user_id:
            continue
        mine = [r for r in sent if r.author_user_id == u.id]
        handled = {r.conversation_id for r in mine}
        frs = [convs[cid].first_response_seconds for cid, (_, author) in first_reply.items()
               if author == u.id and cid in convs and convs[cid].first_response_seconds is not None]
        out.append(AgentStats(
            user_id=u.id, name=f"{u.first_name} {u.last_name}", conversations_handled=len(handled),
            messages_sent=len(mine),
            first_response_p50_seconds=int(percentile(frs, 50)) if frs else None,
            first_response_p90_seconds=int(percentile(frs, 90)) if frs else None,
            sla_breaches=sum(1 for cid in handled
                             if convs.get(cid) and convs[cid].sla_breach_notified_at),
            quick_reply_share=None, work_orders_created=wos.get(u.id, 0)))
    return sorted(out, key=lambda a: -a.messages_sent)
