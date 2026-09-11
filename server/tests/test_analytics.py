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
    # Cross into a new hour AND a new calendar day before the second inbound message, so the
    # inboundByHour/inboundByDay bucketing assertions below cannot pass on an implementation that
    # dumps every message into one bucket (see Tasks 7/13/14 review history for this pattern).
    clock.advance(hours=13)
    second_hour = clock.now()
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "late checkout?")
    agent = login("agent@hvh.test")
    from sqlalchemy import select

    from app.models import Conversation

    with database.session() as db:
        sarah = db.scalar(select(Conversation.id).where(
            Conversation.guest_id == fx.guest_inhouse_a.id))
    clock.advance(minutes=2)
    agent.post(f"/api/p/{fx.property_a.id}/conversations/{sarah}/messages", json={"body": "On it"})
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id,
            source_conversation_id=sarah))
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id,
                               WorkOrderStatus.in_progress)
    clock.advance(minutes=20)
    with database.session() as db:
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id,
                               WorkOrderStatus.complete)
        from app.queue.handlers.sla import sweep_once

        sweep_once(db)  # Diego is now overdue
    mgr = login("manager@hvh.test")
    base = f"/api/p/{fx.property_a.id}/analytics"
    o = mgr.get(f"{base}/overview?from={start.date()}"
               f"&to={(start + timedelta(days=1)).date()}").get_json()
    assert o["conversations"] == 2 and o["inboundMessages"] == 2 and o["outboundMessages"] == 1
    # Sarah's first reply came 13h2m after her inbound message (the clock advances above are
    # cumulative), and Diego never got a reply, so the single first-response value drives both
    # percentiles.
    first_response_seconds = 13 * 3600 + 120
    assert (o["firstResponseP50Seconds"] == first_response_seconds
            and o["firstResponseP90Seconds"] == first_response_seconds)
    assert o["slaBreaches"] == 1
    assert o["slaBreachRate"] == 0.5
    assert (o["workOrdersCreated"] == 1 and o["workOrdersClosed"] == 1
           and o["meanTimeToResolveSeconds"] == 1200)
    assert o["workOrdersFromConversations"] == 1

    hour_counts = {b["hour"]: b["count"] for b in o["inboundByHour"]}
    assert len(o["inboundByHour"]) == 24
    assert hour_counts[start.hour] == 1
    assert hour_counts[second_hour.hour] == 1
    assert start.hour != second_hour.hour
    assert sum(hour_counts.values()) == 2

    day_counts = {b["day"]: b["count"] for b in o["inboundByDay"]}
    assert day_counts == {start.date().isoformat(): 1, second_hour.date().isoformat(): 1}
    assert start.date() != second_hour.date()

    # The whole first-response histogram, not just its existence: 46920s lands in the "30+ min"
    # bucket (the only conversation with a response), every other bucket must be empty.
    dist = {b["label"]: b for b in o["firstResponseDistribution"]}
    assert len(dist) == len(analytics.BUCKETS)
    hit_label = next(label for label, lo, hi in analytics.BUCKETS
                    if lo <= first_response_seconds < hi)
    for label, bucket in dist.items():
        if label == hit_label:
            assert bucket["count"] == 1 and bucket["share"] == 1.0
        else:
            assert bucket["count"] == 0 and bucket["share"] == 0.0

    assert o["workOrdersByDepartment"][0]["departmentName"] == "Engineering"

    a = mgr.get(f"{base}/agents?from={start.date()}"
               f"&to={(start + timedelta(days=1)).date()}").get_json()
    ava = [r for r in a if r["userId"] == fx.agent_a.id][0]
    assert (ava["messagesSent"] == 1 and ava["conversationsHandled"] == 1
           and ava["workOrdersCreated"] == 1)
    assert (ava["firstResponseP50Seconds"] == first_response_seconds
            and ava["firstResponseP90Seconds"] == first_response_seconds)
    assert ava["slaBreaches"] == 0  # Sarah's conversation (the one Ava handled) was never breached
    assert ava["quickReplyShare"] is None  # Phase 1: no quick_reply_id column to derive this from


def test_agent_sees_only_own_stats_and_no_overview(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/analytics"
    agent = login("agent@hvh.test")
    assert agent.get(f"{base}/overview").status_code == 403
    rows = agent.get(f"{base}/agents").get_json()
    assert [r["userId"] for r in rows] == [fx.agent_a.id]


def test_empty_window_returns_zeros_not_500(app, fx, client, login):
    """The property has no conversations, messages, or work orders yet — averages over an empty
    window must come back as sensible zeros/nulls, not a 500 from division by zero."""
    mgr = login("manager@hvh.test")
    base = f"/api/p/{fx.property_a.id}/analytics"
    res = mgr.get(f"{base}/overview")
    assert res.status_code == 200
    o = res.get_json()
    assert o["conversations"] == 0 and o["inboundMessages"] == 0 and o["outboundMessages"] == 0
    assert o["firstResponseP50Seconds"] is None and o["firstResponseP90Seconds"] is None
    assert o["slaBreaches"] == 0 and o["slaBreachRate"] == 0.0
    assert o["workOrdersCreated"] == 0 and o["workOrdersClosed"] == 0
    assert o["meanTimeToResolveSeconds"] is None
    assert o["workOrdersFromConversations"] == 0
    assert o["inboundByDay"] == []
    assert len(o["inboundByHour"]) == 24 and all(b["count"] == 0 for b in o["inboundByHour"])
    assert all(b["count"] == 0 and b["share"] == 0.0 for b in o["firstResponseDistribution"])
    assert o["workOrdersByDepartment"] == []

    rows = mgr.get(f"{base}/agents").get_json()
    assert rows  # property has staff members even though nobody has done anything yet
    for r in rows:
        assert r["messagesSent"] == 0 and r["conversationsHandled"] == 0
        assert r["firstResponseP50Seconds"] is None and r["firstResponseP90Seconds"] is None
        assert (r["slaBreaches"] == 0 and r["quickReplyShare"] is None
               and r["workOrdersCreated"] == 0)


def test_overview_excludes_other_property_data(app, fx, client, database):
    """Cross-property unreachability (test_isolation.py) proves the routes 403 for a non-member.
    It does not prove a member of property A never sees property B's numbers folded into their
    own — that failure mode is silent (no crash, just a wrong number), so it needs its own check."""
    from sqlalchemy import select

    from app.models import Conversation

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "leak under the sink")
    inbound(client, fx, fx.guest_b.phone_e164, "no towels left", to=fx.property_b.sms_number)
    with database.session() as db:
        b_conversation_id = db.scalar(select(Conversation.id).where(
            Conversation.guest_id == fx.guest_b.id))
        work_orders.create(db, fx.property_b.id, fx.admin_b.id, CreateWorkOrder(
            title="Towels", type=WorkOrderType.housekeeping, location_ref="101",
            source_conversation_id=b_conversation_id))
    # default_range's "until" is now(); keep it strictly after the seeded rows
    clock.advance(minutes=1)

    with database.session() as db:
        a_overview = analytics.overview(db, fx.property_a.id)
        b_overview = analytics.overview(db, fx.property_b.id)

    assert a_overview.conversations == 1 and a_overview.inbound_messages == 1
    assert a_overview.work_orders_created == 0
    assert b_overview.conversations == 1 and b_overview.inbound_messages == 1
    assert b_overview.work_orders_created == 1
