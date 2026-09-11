import pytest
from sqlalchemy import select

from app import clock
from app.domain import draft_prompts, work_orders
from app.errors import TransitionError, ValidationFailed
from app.models import Conversation, DraftPrompt, Message, Notification, WorkOrderEvent
from app.schemas.enums import (
    Direction,
    DraftPromptStatus,
    Priority,
    WorkOrderEventType,
    WorkOrderStatus,
    WorkOrderType,
)
from app.schemas.work_orders import CreateWorkOrder
from tests.factories import inbound, make_conversation, make_message


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


@pytest.mark.parametrize("frm,to,ok", [
    ("open", "assigned", True), ("open", "in_progress", True), ("open", "cancelled", True),
    ("open", "complete", False), ("assigned", "in_progress", True), ("assigned", "open", True),
    ("in_progress", "blocked", True), ("in_progress", "complete", True),
    ("blocked", "in_progress", True),
    ("blocked", "complete", False), ("complete", "verified", True),
    ("complete", "in_progress", True),
    ("verified", "open", False), ("cancelled", "open", False),
])
def test_transition_matrix(frm, to, ok):
    if ok:
        work_orders.assert_transition(WorkOrderStatus(frm), WorkOrderStatus(to))
    else:
        with pytest.raises(TransitionError):
            work_orders.assert_transition(WorkOrderStatus(frm), WorkOrderStatus(to))


def test_prefill_from_conversation(app, fx, client, database):
    """§11.1 #6 (prefill half)"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "Hi there")
    clock.advance(minutes=1)
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "The AC in our room isn't working at all")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        p = work_orders.prefill_from_conversation(db, fx.property_a.id, cid)
    assert p.title == "The AC in our room isn't working at all"
    assert "Hi there" in p.description and "AC" in p.description
    assert p.location_ref == "412" and p.guest_name == "Sarah Chen"
    assert p.department_id == fx.dept_engineering.id and p.type == WorkOrderType.maintenance
    assert p.source_conversation_id == cid and p.source_message_id is not None


def test_prefill_with_whitespace_only_body_falls_back_to_guest_request(app, fx, database):
    """Finding 1: a media-only/blank-Body webhook can persist a whitespace-only inbound body
    (see app/channels/mock_sms.py); prefill must not crash on it."""
    with database.session() as db:
        conv = make_conversation(db, fx)
        make_message(db, conv, direction=Direction.inbound, body="   ")
        cid = conv.id
    with database.session() as db:
        p = work_orders.prefill_from_conversation(db, fx.property_a.id, cid)
    assert p.title == "Guest request"


def test_create_from_conversation_stores_source_and_notifies_department(app, fx, client, database,
                                                                        events):
    """§11.1 #6 (create half)"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", description="Guest reports warm room",
            type=WorkOrderType.maintenance,
            priority=Priority.urgent, location_ref="412", department_id=fx.dept_engineering.id,
            source_conversation_id=cid))
        assert wo.status == WorkOrderStatus.open and wo.source_conversation_id == cid
        ev = db.scalars(select(WorkOrderEvent).where(WorkOrderEvent.work_order_id == wo.id)).all()
        assert [e.type.value for e in ev] == ["created"]
        targets = sorted(n.user_id for n in db.scalars(
            select(Notification).where(Notification.type == "work_order.created")).all())
        assert targets == sorted([fx.engineer_a.id, fx.supervisor_a.id])
    assert any(e.type == "work_order.created" for e in events)


def test_create_with_assignee_starts_assigned(app, fx, database):
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.supervisor_a.id, CreateWorkOrder(
            title="Toilet running", type=WorkOrderType.maintenance, location_ref="221",
            department_id=fx.dept_engineering.id, assigned_user_id=fx.engineer_a.id))
        assert wo.status == WorkOrderStatus.assigned and wo.assigned_user_id == fx.engineer_a.id
        n = db.scalar(select(Notification).where(Notification.type == "work_order.assigned"))
        assert n.user_id == fx.engineer_a.id


def test_assign_reassigns_and_notifies_new_assignee(app, fx, database):
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.supervisor_a.id, CreateWorkOrder(
            title="Leaky faucet", type=WorkOrderType.maintenance, location_ref="303",
            department_id=fx.dept_engineering.id, assigned_user_id=fx.engineer_a.id))
        wo_id = wo.id
    with database.session() as db:
        wo = work_orders.assign(db, fx.property_a.id, wo_id, fx.supervisor_a.id,
                                user_id=fx.housekeeper_a.id)
        assert wo.assigned_user_id == fx.housekeeper_a.id and wo.status == WorkOrderStatus.assigned
        n = db.scalar(select(Notification).where(Notification.type == "work_order.assigned",
                                                  Notification.user_id == fx.housekeeper_a.id))
        assert n is not None
        # Filter by type rather than position: "created" and "assigned" share a created_at under
        # the frozen clock, and their relative order between two rows with unrelated (random)
        # primary keys is not something this query's ORDER BY guarantees.
        assigned_ev = db.scalar(select(WorkOrderEvent).where(
            WorkOrderEvent.work_order_id == wo_id,
            WorkOrderEvent.type == WorkOrderEventType.assigned))
        assert assigned_ev is not None
        assert (assigned_ev.from_value == fx.engineer_a.id
               and assigned_ev.to_value == fx.housekeeper_a.id)


def test_complete_creates_unsent_editable_draft_prompt(app, fx, client, database, events):
    """§11.1 #7"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id, source_conversation_id=cid))
        wo_id = wo.id
        msgs_before = len(db.scalars(select(Message)).all())
    clock.advance(minutes=1)
    with database.session() as db:
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id,
                               WorkOrderStatus.in_progress)
    clock.advance(minutes=14)
    with database.session() as db:
        wo = work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id,
                                    WorkOrderStatus.complete,
                                    comment="Cleared condensate line")
        assert wo.completed_at == clock.now() and wo.started_at is not None
        prompts = db.scalars(select(DraftPrompt).where(DraftPrompt.conversation_id == cid)).all()
        assert len(prompts) == 1 and prompts[0].status == DraftPromptStatus.pending
        assert "Sarah" in prompts[0].body and "412" in prompts[0].body
        assert len(db.scalars(select(Message)).all()) == msgs_before  # nothing was sent
        types = [e.type.value for e in db.scalars(
            select(WorkOrderEvent).where(WorkOrderEvent.work_order_id == wo_id)
            .order_by(WorkOrderEvent.created_at)).all()]
        assert types == ["created", "status_changed", "status_changed"]
    assert any(e.type == "draft_prompt.created" for e in events)
    assert any(e.type == "work_order.updated" for e in events)


def test_complete_without_source_conversation_creates_no_prompt(app, fx, database):
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.supervisor_a.id, CreateWorkOrder(
            title="Hallway light", type=WorkOrderType.maintenance, location_ref="5F"))
        work_orders.transition(db, fx.property_a.id, wo.id, fx.supervisor_a.id,
                               WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo.id, fx.supervisor_a.id,
                               WorkOrderStatus.complete)
        assert db.scalars(select(DraftPrompt)).all() == []


def test_sending_the_draft_marks_prompt_sent_and_guest_notified(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id, source_conversation_id=cid))
        wo_id = wo.id
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id,
                               WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id,
                               WorkOrderStatus.complete)
        pid = db.scalar(select(DraftPrompt.id).where(DraftPrompt.conversation_id == cid))
    c = login("agent@hvh.test")
    d = c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()
    assert (d["draftPrompts"][0]["id"] == pid
           and d["draftPrompts"][0]["workOrderTitle"] == "AC not cooling")
    res = c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                 json={"body": "Hi Sarah — fixed!", "draftPromptId": pid})
    assert res.status_code == 201
    with database.session() as db:
        assert db.get(DraftPrompt, pid).status == DraftPromptStatus.sent
        from app.models import WorkOrder

        assert db.get(WorkOrder, wo_id).guest_notified_at is not None
    assert c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()["draftPrompts"] == []


def test_dismiss_prompt_transitions_and_is_noop_once_sent(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id, source_conversation_id=cid))
        wo_id = wo.id
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id,
                               WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id,
                               WorkOrderStatus.complete)
        pid = db.scalar(select(DraftPrompt.id).where(DraftPrompt.conversation_id == cid))
    with database.session() as db:
        dp = draft_prompts.dismiss(db, fx.property_a.id, cid, pid, fx.agent_a.id)
        assert dp.status == DraftPromptStatus.dismissed
        assert dp.resolved_at == clock.now() and dp.resolved_by_user_id == fx.agent_a.id

    # A second, unrelated prompt that has already been sent must not be flipped by dismiss().
    c = login("agent@hvh.test")
    with database.session() as db:
        wo2 = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="Toilet still running", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id, source_conversation_id=cid))
        wo2_id = wo2.id
        work_orders.transition(db, fx.property_a.id, wo2_id, fx.engineer_a.id,
                               WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo2_id, fx.engineer_a.id,
                               WorkOrderStatus.complete)
        pid2 = db.scalar(select(DraftPrompt.id).where(DraftPrompt.work_order_id == wo2_id))
    res = c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                 json={"body": "Fixed the toilet too!", "draftPromptId": pid2})
    assert res.status_code == 201
    with database.session() as db:
        sent_at_before = db.get(DraftPrompt, pid2).resolved_at
    clock.advance(minutes=1)
    with database.session() as db:
        dp2 = draft_prompts.dismiss(db, fx.property_a.id, cid, pid2, fx.supervisor_a.id)
        # unchanged: dismiss only acts on pending prompts
        assert dp2.status == DraftPromptStatus.sent
        assert dp2.resolved_at == sent_at_before and dp2.resolved_by_user_id == fx.agent_a.id


def test_detail_renders_event_timeline(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id, source_conversation_id=cid))
        wo_id = wo.id
    clock.advance(minutes=1)
    with database.session() as db:
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id,
                               WorkOrderStatus.in_progress, comment="On it")
    with database.session() as db:
        d = work_orders.detail(db, fx.property_a.id, wo_id)
        assert d.id == wo_id and d.guest_name == "Sarah Chen" and d.room_number == "412"
        assert [e.type.value for e in d.events] == ["created", "status_changed"]
        assert d.events[1].comment == "On it" and d.events[1].user_name == "Eli Engineer"


def test_invalid_transition_is_409_and_audited(app, fx, database):
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.supervisor_a.id, CreateWorkOrder(
            title="x", type=WorkOrderType.other, location_ref="lobby"))
        with pytest.raises(TransitionError):
            work_orders.transition(db, fx.property_a.id, wo.id, fx.supervisor_a.id,
                                   WorkOrderStatus.complete)
        assert wo.status == WorkOrderStatus.open  # rejected transition left the row untouched
        ev = db.scalars(select(WorkOrderEvent).where(WorkOrderEvent.work_order_id == wo.id)).all()
        # no spurious status_changed event was written
        assert [e.type.value for e in ev] == ["created"]


def test_list_rejects_unknown_status_filter(app, fx, database):
    """Finding 5: an unrecognized status token in the filter must not escape as a bare 500."""
    with database.session() as db:
        with pytest.raises(ValidationFailed):
            work_orders.list(db, fx.property_a.id, status="bogus")


def test_department_keyword_guess():
    from app.domain.work_orders import guess_department_type

    assert guess_department_type("the ac is broken and it's hot") == "engineering"
    assert guess_department_type("could we get extra towels and pillows") == "housekeeping"
    assert guess_department_type("late checkout please") == "front_desk"
    assert guess_department_type("hello") is None
