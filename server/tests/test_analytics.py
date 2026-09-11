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
