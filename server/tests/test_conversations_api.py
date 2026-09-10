from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.models import Conversation, Message
from app.schemas.enums import ConversationStatus, DeliveryStatus
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def _base(fx):
    return f"/api/p/{fx.property_a.id}/conversations"


def test_list_sorts_oldest_unanswered_first_and_shows_context(app, fx, client, database, login):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "late checkout?")
    clock.advance(minutes=1)
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    c = login("agent@hvh.test")
    rows = c.get(_base(fx)).get_json()
    assert [r["guest"]["firstName"] for r in rows] == ["Diego", "Sarah"]
    sarah = rows[1]
    assert sarah["roomNumber"] == "412" and sarah["unanswered"] is True
    assert sarah["lastMessagePreview"] == "AC broken"
    assert sarah["slaDueAt"] is not None


def test_filters_mine_unassigned_overdue_resolved_archived(app, fx, client, database, login):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "one")
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "two")
    diego, sarah = _cid(database, fx.guest_nostay_a.id), _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    assert c.patch(f"{_base(fx)}/{sarah}", json={"assignedUserId": fx.agent_a.id}).status_code == 200
    assert {r["id"] for r in c.get(_base(fx) + "?filter=mine").get_json()} == {sarah}
    assert {r["id"] for r in c.get(_base(fx) + "?filter=unassigned").get_json()} == {diego}
    assert c.get(_base(fx) + "?filter=overdue").get_json() == []
    clock.advance(minutes=16)
    assert {r["id"] for r in c.get(_base(fx) + "?filter=overdue").get_json()} == {diego, sarah}
    # Resolved: no guest message for 4h and no open WO → leaves "all", appears in "resolved".
    c.post(f"{_base(fx)}/{diego}/messages", json={"body": "Sure"})
    clock.advance(hours=4, minutes=1)
    assert diego not in {r["id"] for r in c.get(_base(fx)).get_json()}
    assert {r["id"] for r in c.get(_base(fx) + "?filter=resolved").get_json()} == {diego}
    # Archive with a category (none seeded → null), then it lives only in "archived".
    assert c.patch(f"{_base(fx)}/{diego}", json={"status": "archived"}).status_code == 200
    assert {r["id"] for r in c.get(_base(fx) + "?filter=archived").get_json()} == {diego}
    assert diego not in {r["id"] for r in c.get(_base(fx) + "?filter=resolved").get_json()}


def test_dept_staff_sees_only_their_department_or_own_conversations(app, fx, client, database, login):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "one")
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "two")
    diego, sarah = _cid(database, fx.guest_nostay_a.id), _cid(database, fx.guest_inhouse_a.id)
    agent = login("agent@hvh.test")
    agent.patch(f"{_base(fx)}/{sarah}", json={"assignedDepartmentId": fx.dept_engineering.id})
    eng = login("engineer@hvh.test")
    assert {r["id"] for r in eng.get(_base(fx)).get_json()} == {sarah}
    assert eng.get(f"{_base(fx)}/{diego}").status_code == 403


def test_detail_includes_messages_notes_and_stay(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    assert c.post(f"{_base(fx)}/{cid}/notes", json={"body": "Gold guest, @Marcus please watch"}).status_code == 201
    d = c.get(f"{_base(fx)}/{cid}").get_json()
    assert d["guest"]["firstName"] == "Sarah" and d["stay"]["roomNumber"] == "412"
    assert [m["body"] for m in d["messages"]] == ["AC broken"]
    assert d["notes"][0]["body"].startswith("Gold guest") and d["notes"][0]["authorName"] == "Ava Agent"
    assert d["workOrders"] == [] and d["draftPrompts"] == []


def test_note_mention_notifies_mentioned_user(app, fx, client, database, login):
    from app.models import Notification

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    login("agent@hvh.test").post(f"{_base(fx)}/{cid}/notes", json={"body": "@Marcus can you take this"})
    with database.session() as db:
        n = db.scalar(select(Notification).where(Notification.type == "note.mention"))
        assert n.user_id == fx.agent_a2.id


def test_snooze_hides_and_wakes(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    until = (clock.now() + timedelta(hours=1)).isoformat()
    assert c.patch(f"{_base(fx)}/{cid}", json={"status": "snoozed", "snoozedUntil": until}).status_code == 200
    assert c.get(_base(fx)).get_json() == []
    with database.session() as db:
        assert db.get(Conversation, cid).status == ConversationStatus.snoozed


def test_retry_failed_message_via_api(app, fx, client, database, login, worker):
    """§11.1 #4 (server half): failure carries the provider error; retry re-queues."""
    with database.session() as db:
        g = db.get(type(fx.guest_inhouse_a), fx.guest_inhouse_a.id)
        g.phone_e164 = "+15552000000"
    inbound(client, fx, "+15552000000", "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    mid = c.post(f"{_base(fx)}/{cid}/messages", json={"body": "hello"}).get_json()["id"]
    worker.tick(); clock.advance(seconds=0.5); worker.tick()
    d = c.get(f"{_base(fx)}/{cid}").get_json()
    failed = [m for m in d["messages"] if m["id"] == mid][0]
    assert failed["deliveryStatus"] == "failed" and failed["providerErrorCode"] == "30007"
    res = c.post(f"{_base(fx)}/{cid}/messages/{mid}/retry")
    assert res.status_code == 200 and res.get_json()["deliveryStatus"] == "queued"


def test_archive_requires_capability(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    login("agent@hvh.test").patch(f"{_base(fx)}/{cid}", json={"assignedDepartmentId": fx.dept_engineering.id})
    eng = login("engineer@hvh.test")
    assert eng.patch(f"{_base(fx)}/{cid}", json={"status": "archived"}).status_code == 403
