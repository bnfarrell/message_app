"""Guest identity must not leave through a route that skips the conversation viewer check.

Probed against the running server during the whole-branch review: an engineer (dept_staff,
Engineering) who is 403'd from a housekeeping conversation could still read that conversation's
guest name and room number back out of the work order raised from it, and could read the guest's
phone number, loyalty tier, consent status, stay history and conversation ids from
GET /guests/<id>.

The ruling that shapes these tests: property-wide work-order *visibility* and *mutation* stand —
design.md §3.2 has no work-order-viewing capability and that is the documented design. What does
not stand is reaching *through* `source_conversation_id` to surface conversation-derived guest
fields to a viewer who was just refused that conversation.
"""
from sqlalchemy import select

from app.models import Conversation
from tests.factories import inbound


def _housekeeping_case(fx, client, database, login):
    """An inbound conversation assigned to Housekeeping, plus a work order raised from it."""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "Please send more towels to 412")
    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(
            Conversation.guest_id == fx.guest_inhouse_a.id))
    agent = login("agent@hvh.test")
    base = f"/api/p/{fx.property_a.id}"
    assert agent.patch(f"{base}/conversations/{cid}",
                       json={"assignedDepartmentId": fx.dept_housekeeping.id}).status_code == 200
    wo = agent.post(f"{base}/work-orders", json={
        "title": "Towels", "type": "housekeeping", "locationRef": "412",
        "departmentId": fx.dept_housekeeping.id, "sourceConversationId": cid}).get_json()
    return base, cid, wo, agent


def test_work_order_detail_hides_conversation_derived_guest_fields(app, fx, client, database,
                                                                   login):
    base, cid, wo, agent = _housekeeping_case(fx, client, database, login)
    eng = login("engineer@hvh.test")  # dept_staff, Engineering

    assert eng.get(f"{base}/conversations/{cid}").status_code == 403

    d = eng.get(f"{base}/work-orders/{wo['id']}")
    assert d.status_code == 200, "property-wide work-order visibility must still stand"
    body = d.get_json()
    assert body["guestName"] is None
    assert body["roomNumber"] == "412"  # the work order's own locationRef, not the stay's room
    assert body["title"] == "Towels"

    # Mutation stands too (the ruling is deliberately narrow), and the response to the mutation
    # must not leak the fields either.
    patched = eng.patch(f"{base}/work-orders/{wo['id']}", json={"priority": "urgent"})
    assert patched.status_code == 200 and patched.get_json()["guestName"] is None

    # A viewer who can see the conversation still gets them.
    assert agent.get(f"{base}/work-orders/{wo['id']}").get_json()["guestName"] == "Sarah Chen"


def test_work_order_detail_shows_guest_fields_to_the_assigned_department(app, fx, client,
                                                                         database, login):
    """Guards the previous test against over-correction: housekeeping staff are allowed to see
    the conversation, so they must still get the guest name and the stay's room number."""
    base, cid, wo, _ = _housekeeping_case(fx, client, database, login)
    hk = login("housekeeper@hvh.test")
    assert hk.get(f"{base}/conversations/{cid}").status_code == 200
    body = hk.get(f"{base}/work-orders/{wo['id']}").get_json()
    assert body["guestName"] == "Sarah Chen" and body["roomNumber"] == "412"


def test_guest_detail_requires_view_all_conversations(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    path = f"/api/p/{fx.property_a.id}/guests/{fx.guest_inhouse_a.id}"

    eng = login("engineer@hvh.test")  # dept_staff: the one staff role without the capability
    assert eng.get(path).status_code == 403

    for email in ("agent@hvh.test", "supervisor@hvh.test", "manager@hvh.test", "admin@hvh.test",
                  "corporate@hvh.test"):
        res = login(email).get(path)
        assert res.status_code == 200, email
        assert res.get_json()["guest"]["phoneE164"] == fx.guest_inhouse_a.phone_e164
