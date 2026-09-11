from sqlalchemy import select

from app.models import Conversation
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def test_prefill_create_transition_and_detail_via_api(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "The AC in our room isn't working")
    cid = _cid(database, fx.guest_inhouse_a.id)
    base = f"/api/p/{fx.property_a.id}/work-orders"
    agent = login("agent@hvh.test")
    p = agent.get(f"{base}/prefill?conversationId={cid}").get_json()
    assert p["locationRef"] == "412" and p["departmentId"] == fx.dept_engineering.id
    res = agent.post(base, json={**{k: p[k] for k in ("title", "description", "type", "priority", "locationType",
                                                           "locationRef", "departmentId", "sourceConversationId",
                                                           "sourceMessageId")}, "priority": "urgent"})
    assert res.status_code == 201
    wo = res.get_json()
    assert wo["status"] == "open" and wo["sourceConversationId"] == cid
    eng = login("engineer@hvh.test")
    assert eng.patch(f"{base}/{wo['id']}", json={"assignedUserId": fx.engineer_a.id}).get_json()["status"] == "assigned"
    assert eng.patch(f"{base}/{wo['id']}", json={"status": "in_progress"}).get_json()["status"] == "in_progress"
    bad = eng.patch(f"{base}/{wo['id']}", json={"status": "verified"})
    assert bad.status_code == 409 and bad.get_json()["error"]["code"] == "INVALID_TRANSITION"
    done = eng.patch(f"{base}/{wo['id']}", json={"status": "complete", "comment": "Cleared drain line"})
    assert done.status_code == 200
    d = eng.get(f"{base}/{wo['id']}").get_json()
    assert [e["type"] for e in d["events"]] == ["created", "assigned", "status_changed", "status_changed"]
    assert d["events"][-1]["comment"] == "Cleared drain line" and d["guestName"] == "Sarah Chen"
    assert d["events"][1]["userName"] == "Eli Engineer"


def test_close_requires_capability_but_create_does_not(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/work-orders"
    agent = login("agent@hvh.test")
    wo = agent.post(base, json={"title": "Lamp", "type": "maintenance", "locationRef": "330"}).get_json()
    agent.patch(f"{base}/{wo['id']}", json={"status": "in_progress"})
    assert agent.patch(f"{base}/{wo['id']}", json={"status": "complete"}).status_code == 403
    sup = login("supervisor@hvh.test")
    assert sup.patch(f"{base}/{wo['id']}", json={"status": "complete"}).status_code == 200


def test_list_filters(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/work-orders"
    sup = login("supervisor@hvh.test")
    a = sup.post(base, json={"title": "A", "type": "maintenance", "locationRef": "1", "assignedUserId": fx.engineer_a.id}).get_json()
    b = sup.post(base, json={"title": "B", "type": "housekeeping", "locationRef": "2", "departmentId": fx.dept_housekeeping.id}).get_json()
    sup.patch(f"{base}/{b['id']}", json={"status": "cancelled"})
    ids = lambda r: {w["id"] for w in r.get_json()}  # noqa: E731
    assert ids(sup.get(base)) == {a["id"]}
    assert ids(sup.get(base + "?includeClosed=true")) == {a["id"], b["id"]}
    assert ids(sup.get(base + "?status=cancelled")) == {b["id"]}
    eng = login("engineer@hvh.test")
    assert ids(eng.get(base + "?mine=true")) == {a["id"]}
    assert ids(sup.get(base + f"?dept={fx.dept_housekeeping.id}&includeClosed=true")) == {b["id"]}


def test_dismiss_draft_prompt(app, fx, client, database, login):
    from app.domain import work_orders
    from app.schemas.enums import WorkOrderStatus, WorkOrderType
    from app.schemas.work_orders import CreateWorkOrder

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC", type=WorkOrderType.maintenance, locationRef="412", sourceConversationId=cid))
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.complete)
    c = login("agent@hvh.test")
    pid = c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()["draftPrompts"][0]["id"]
    assert c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/draft-prompts/{pid}/dismiss").status_code == 204
    assert c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()["draftPrompts"] == []
