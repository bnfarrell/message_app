### Task 18: Analytics

**Files:**
- Create: `server/app/domain/analytics.py`, `server/app/schemas/analytics.py`, `server/app/api/analytics.py`, `server/tests/test_analytics.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces: `analytics.overview(db, property_id, since, until) -> Overview`; `analytics.agents(db, property_id, since, until) -> list[AgentStats]`; `analytics.percentile(values, p) -> float | None` (nearest-rank). Routes `GET analytics/overview?from=&to=` and `GET analytics/agents?from=&to=` (`view_property_analytics`; `view_own_stats` users get `agents` filtered to themselves). ISO dates or datetimes; default last 7 days.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_analytics.py`:
```python
from datetime import timedelta

from app import clock
from app.domain import analytics, work_orders
from app.schemas.enums import WorkOrderStatus, WorkOrderType
from app.schemas.work_orders import CreateWorkOrder
from tests.factories import inbound


def test_percentile_nearest_rank():
    assert analytics.percentile([], 50) is None
    assert analytics.percentile([10], 90) == 10
    assert analytics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert analytics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9


def test_overview_and_agents(app, fx, client, database, login):
    start = clock.now()
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "late checkout?")
    agent = login("agent@hvh.test")
    from sqlalchemy import select

    from app.models import Conversation

    with database.session() as db:
        sarah = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        diego = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_nostay_a.id))
    clock.advance(minutes=2)
    agent.post(f"/api/p/{fx.property_a.id}/conversations/{sarah}/messages", json={"body": "On it"})
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC", type=WorkOrderType.maintenance, location_ref="412", department_id=fx.dept_engineering.id,
            source_conversation_id=sarah))
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.in_progress)
    clock.advance(minutes=20)
    with database.session() as db:
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.complete)
        from app.queue.handlers.sla import sweep_once

        sweep_once(db)  # Diego is now overdue
    mgr = login("manager@hvh.test")
    base = f"/api/p/{fx.property_a.id}/analytics"
    o = mgr.get(f"{base}/overview?from={start.date()}&to={(start + timedelta(days=1)).date()}").get_json()
    assert o["conversations"] == 2 and o["inboundMessages"] == 2 and o["outboundMessages"] == 1
    assert o["firstResponseP50Seconds"] == 120 and o["firstResponseP90Seconds"] == 120
    assert o["slaBreaches"] == 1
    assert o["workOrdersCreated"] == 1 and o["workOrdersClosed"] == 1 and o["meanTimeToResolveSeconds"] == 1200
    assert o["workOrdersFromConversations"] == 1
    assert sum(b["count"] for b in o["inboundByHour"]) == 2 and len(o["inboundByHour"]) == 24
    assert o["workOrdersByDepartment"][0]["departmentName"] == "Engineering"
    a = mgr.get(f"{base}/agents?from={start.date()}&to={(start + timedelta(days=1)).date()}").get_json()
    ava = [r for r in a if r["userId"] == fx.agent_a.id][0]
    assert ava["messagesSent"] == 1 and ava["conversationsHandled"] == 1 and ava["workOrdersCreated"] == 1
    assert ava["firstResponseP50Seconds"] == 120


def test_agent_sees_only_own_stats_and_no_overview(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/analytics"
    agent = login("agent@hvh.test")
    assert agent.get(f"{base}/overview").status_code == 403
    rows = agent.get(f"{base}/agents").get_json()
    assert [r["userId"] for r in rows] == [fx.agent_a.id]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_analytics.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write schemas, domain, route**

`app/schemas/analytics.py`:
```python
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
```

`app/domain/analytics.py`:
```python
"""Aggregations are computed in Python from narrow selects so they run identically on SQLite and Postgres."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Conversation, Department, Message, PropertyMembership, UserAccount, WorkOrder
from app.schemas.analytics import (AgentStats, DayBucket, DepartmentBucket, HourBucket, Overview, ResponseBucket)
from app.schemas.enums import AuthorType, Direction, WorkOrderStatus

CLOSED = (WorkOrderStatus.complete, WorkOrderStatus.verified)
BUCKETS = [("< 2 min", 0, 120), ("2–5 min", 120, 300), ("5–15 min", 300, 900), ("15–30 min", 900, 1800),
           ("30+ min", 1800, 10**9)]


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


def overview(db: Session, property_id: str, since: datetime | None = None, until: datetime | None = None) -> Overview:
    since, until = default_range(since, until)
    convs = db.scalars(select(Conversation).where(Conversation.property_id == property_id,
                                                  Conversation.created_at >= since, Conversation.created_at < until)).all()
    msgs = db.execute(select(Message.direction, Message.sent_at, Message.author_type).where(
        Message.property_id == property_id, Message.sent_at >= since, Message.sent_at < until)).all()
    inbound = [m for m in msgs if m.direction == Direction.inbound]
    outbound = [m for m in msgs if m.direction == Direction.outbound and m.author_type == AuthorType.staff]
    frs = [c.first_response_seconds for c in convs if c.first_response_seconds is not None]
    breaches = sum(1 for c in convs if c.sla_breach_notified_at is not None)
    by_hour = Counter(m.sent_at.hour for m in inbound)
    by_day = Counter(m.sent_at.date().isoformat() for m in inbound)
    dist = [ResponseBucket(label=label, count=sum(1 for v in frs if lo <= v < hi),
                           share=(sum(1 for v in frs if lo <= v < hi) / len(frs)) if frs else 0.0)
            for label, lo, hi in BUCKETS]
    wos_created = db.scalars(select(WorkOrder).where(WorkOrder.property_id == property_id,
                                                     WorkOrder.created_at >= since, WorkOrder.created_at < until)).all()
    wos_closed = db.scalars(select(WorkOrder).where(WorkOrder.property_id == property_id, WorkOrder.status.in_(CLOSED),
                                                    WorkOrder.completed_at >= since, WorkOrder.completed_at < until)).all()
    ttr = [(w.completed_at - w.created_at).total_seconds() for w in wos_closed if w.completed_at]
    dept_names = {d.id: d.name for d in db.scalars(select(Department).where(Department.property_id == property_id)).all()}
    per_dept: dict[str | None, list[float]] = defaultdict(list)
    for w in wos_closed:
        per_dept[w.department_id].append((w.completed_at - w.created_at).total_seconds())
    dept_rows = sorted(
        [DepartmentBucket(department_id=d, department_name=dept_names.get(d, "Unassigned"), closed=len(v),
                          mean_time_to_resolve_seconds=int(sum(v) / len(v)) if v else None) for d, v in per_dept.items()],
        key=lambda r: -r.closed)
    return Overview(
        since=since, until=until, conversations=len(convs), inbound_messages=len(inbound), outbound_messages=len(outbound),
        first_response_p50_seconds=int(percentile(frs, 50)) if frs else None,
        first_response_p90_seconds=int(percentile(frs, 90)) if frs else None,
        sla_breaches=breaches, sla_breach_rate=(breaches / len(convs)) if convs else 0.0,
        work_orders_created=len(wos_created), work_orders_closed=len(wos_closed),
        work_orders_from_conversations=sum(1 for w in wos_created if w.source_conversation_id),
        mean_time_to_resolve_seconds=int(sum(ttr) / len(ttr)) if ttr else None,
        inbound_by_hour=[HourBucket(hour=h, count=by_hour.get(h, 0)) for h in range(24)],
        inbound_by_day=[DayBucket(day=d, count=n) for d, n in sorted(by_day.items())],
        first_response_distribution=dist, work_orders_by_department=dept_rows)


def agents(db: Session, property_id: str, since: datetime | None = None, until: datetime | None = None,
           only_user_id: str | None = None) -> list[AgentStats]:
    since, until = default_range(since, until)
    staff = db.execute(select(UserAccount, PropertyMembership).join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
                       .where(PropertyMembership.property_id == property_id)).all()
    sent = db.execute(select(Message.author_user_id, Message.conversation_id, Message.sent_at).where(
        Message.property_id == property_id, Message.direction == Direction.outbound, Message.author_type == AuthorType.staff,
        Message.sent_at >= since, Message.sent_at < until)).all()
    first_reply: dict[str, tuple[datetime, str]] = {}
    for author, conv_id, at in sorted(sent, key=lambda r: r.sent_at):
        first_reply.setdefault(conv_id, (at, author))
    convs = {c.id: c for c in db.scalars(select(Conversation).where(Conversation.property_id == property_id)).all()}
    wos = Counter(w.reported_by_user_id for w in db.scalars(select(WorkOrder).where(
        WorkOrder.property_id == property_id, WorkOrder.created_at >= since, WorkOrder.created_at < until)).all())
    out = []
    for u, m in staff:
        if only_user_id and u.id != only_user_id:
            continue
        mine = [r for r in sent if r.author_user_id == u.id]
        handled = {r.conversation_id for r in mine}
        frs = [convs[cid].first_response_seconds for cid, (_, author) in first_reply.items()
               if author == u.id and cid in convs and convs[cid].first_response_seconds is not None]
        out.append(AgentStats(
            user_id=u.id, name=f"{u.first_name} {u.last_name}", conversations_handled=len(handled),
            messages_sent=len(mine), first_response_p50_seconds=int(percentile(frs, 50)) if frs else None,
            first_response_p90_seconds=int(percentile(frs, 90)) if frs else None,
            sla_breaches=sum(1 for cid in handled if convs.get(cid) and convs[cid].sla_breach_notified_at),
            quick_reply_share=None, work_orders_created=wos.get(u.id, 0)))
    return sorted(out, key=lambda a: -a.messages_sent)
```

(`quick_reply_share` stays `None` in Phase 1 — messages don't record which quick reply produced them; the web plan may add a `quick_reply_id` column later.)

`app/api/analytics.py`:
```python
from datetime import datetime, time, timezone

from flask import Blueprint, g, request

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import analytics
from app.errors import Forbidden, ValidationFailed

bp = Blueprint("analytics", __name__, url_prefix="/api/p/<property_id>/analytics")


def _parse(name: str, end_of_day: bool = False) -> datetime | None:
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as e:
        raise ValidationFailed(f"{name} must be an ISO date or datetime") from e
    if dt.tzinfo is None:
        dt = datetime.combine(dt.date(), time.max if end_of_day and len(raw) == 10 else dt.time(), tzinfo=timezone.utc)
    return dt


@bp.get("/overview")
@require_auth
@require_property
@require_capability("view_property_analytics")
def overview(property_id: str):
    with db_session() as db:
        return ok(analytics.overview(db, g.property_id, _parse("from"), _parse("to", end_of_day=True)))


@bp.get("/agents")
@require_auth
@require_property
def agents(property_id: str):
    role = g.membership.role
    if has_capability(role, "view_property_analytics"):
        only = None
    elif has_capability(role, "view_own_stats"):
        only = g.user.id
    else:
        raise Forbidden("Your role cannot view analytics")
    with db_session() as db:
        return ok(analytics.agents(db, g.property_id, _parse("from"), _parse("to", end_of_day=True), only_user_id=only))
```

Register `analytics.bp`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): analytics overview and per-agent stats"
```

---

