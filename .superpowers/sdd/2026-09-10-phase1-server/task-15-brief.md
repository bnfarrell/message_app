### Task 15: Work orders API and draft-prompt dismiss

**Files:**
- Create: `server/app/api/work_orders.py`, `server/tests/test_work_orders_api.py`
- Modify: `server/app/api/conversations.py` (dismiss route), `server/app/__init__.py`

**Interfaces:**
- Produces routes: `GET work-orders`, `GET work-orders/prefill?conversationId=`, `POST work-orders`, `GET work-orders/<id>`, `PATCH work-orders/<id>` (status | assignedUserId | departmentId | priority | comment | clearAssignee), `POST conversations/<id>/draft-prompts/<pid>/dismiss`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_work_orders_api.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_work_orders_api.py -q`
Expected: FAIL with 404s.

- [ ] **Step 3: Write `app/api/work_orders.py`**

```python
from flask import Blueprint, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import work_orders
from app.errors import Forbidden, ValidationFailed
from app.schemas.enums import WorkOrderStatus
from app.schemas.work_orders import CreateWorkOrder, WorkOrderListQuery, WorkOrderOut, WorkOrderPatch

bp = Blueprint("work_orders", __name__, url_prefix="/api/p/<property_id>/work-orders")
CLOSING = {WorkOrderStatus.complete, WorkOrderStatus.verified, WorkOrderStatus.cancelled}


@bp.get("")
@require_auth
@require_property
def list_work_orders(property_id: str):
    q = parse_query(WorkOrderListQuery)
    with db_session() as db:
        return ok(work_orders.list(db, g.property_id, status=q.status, type=q.type, dept=q.dept,
                                   assignee=q.assignee, mine_user_id=g.user.id if q.mine else None,
                                   include_closed=q.include_closed))


@bp.get("/prefill")
@require_auth
@require_property
@require_capability("create_work_order")
def prefill(property_id: str):
    conversation_id = request.args.get("conversationId")
    if not conversation_id:
        raise ValidationFailed("conversationId is required")
    with db_session() as db:
        return ok(work_orders.prefill_from_conversation(db, g.property_id, conversation_id))


@bp.post("")
@require_auth
@require_property
@require_capability("create_work_order")
def create_work_order(property_id: str):
    data = parse_body(CreateWorkOrder)
    with db_session() as db:
        wo = work_orders.create(db, g.property_id, g.user.id, data)
        return ok(WorkOrderOut.model_validate(wo), 201)


@bp.get("/<work_order_id>")
@require_auth
@require_property
def get_work_order(property_id: str, work_order_id: str):
    with db_session() as db:
        return ok(work_orders.detail(db, g.property_id, work_order_id))


@bp.patch("/<work_order_id>")
@require_auth
@require_property
def patch_work_order(property_id: str, work_order_id: str):
    p = parse_body(WorkOrderPatch)
    with db_session() as db:
        if p.assigned_user_id or p.department_id or p.clear_assignee:
            work_orders.assign(db, g.property_id, work_order_id, g.user.id, user_id=p.assigned_user_id,
                               department_id=p.department_id, clear=p.clear_assignee)
        if p.priority is not None:
            work_orders.set_priority(db, g.property_id, work_order_id, g.user.id, p.priority)
        if p.status is not None:
            if p.status in CLOSING and not has_capability(g.membership.role, "close_work_order"):
                raise Forbidden("Your role cannot close work orders")
            work_orders.transition(db, g.property_id, work_order_id, g.user.id, p.status, comment=p.comment)
        elif p.comment:
            work_orders.comment(db, g.property_id, work_order_id, g.user.id, p.comment)
        return ok(work_orders.detail(db, g.property_id, work_order_id))
```

Add the dismiss route to `app/api/conversations.py`:
```python
from app.domain import draft_prompts


@bp.post("/<conversation_id>/draft-prompts/<prompt_id>/dismiss")
@require_auth
@require_property
@require_capability("reply")
def dismiss_prompt(property_id: str, conversation_id: str, prompt_id: str):
    with db_session() as db:
        draft_prompts.dismiss(db, g.property_id, conversation_id, prompt_id, g.user.id)
    return no_content()
```

Register `work_orders.bp` in `create_app`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass (isolation suite now covers five more routes).

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): work order API with prefill, transitions, filters; draft-prompt dismiss"
```

---

