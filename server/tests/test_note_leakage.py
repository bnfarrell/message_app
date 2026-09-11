"""§11.1 #10: an internal note never appears in any guest-facing payload."""
import json

from pydantic import ValidationError

from app.domain import conversations
from app.schemas.conversations import GuestThread
from tests.factories import inbound

SECRET = "SECRET-NOTE-do-not-leak-7f3a"


def test_guest_thread_excludes_notes_entirely(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    from sqlalchemy import select

    from app.models import Conversation

    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(
            Conversation.guest_id == fx.guest_inhouse_a.id))
    c = login("agent@hvh.test")
    c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/notes", json={"body": SECRET})
    c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
           json={"body": "visible reply"})
    with database.session() as db:
        thread = conversations.guest_thread(db, fx.property_a.id, fx.guest_inhouse_a.phone_e164)
    payload = json.dumps(thread.model_dump(mode="json", by_alias=True))
    assert SECRET not in payload
    assert "visible reply" in payload
    assert "note" not in payload.lower()


def test_guest_thread_schema_rejects_a_notes_field():
    try:
        GuestThread.model_validate({"phone": "+1", "propertyName": "x", "messages": [],
                                    "notes": []})
    except ValidationError:
        return
    raise AssertionError("GuestThread accepted a 'notes' field — it must be extra='forbid'")


def test_staff_detail_keeps_notes_in_a_separate_array(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    from sqlalchemy import select

    from app.models import Conversation

    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(
            Conversation.guest_id == fx.guest_inhouse_a.id))
    c = login("agent@hvh.test")
    c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/notes", json={"body": SECRET})
    d = c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()
    assert all(SECRET not in m["body"] for m in d["messages"])
    assert d["notes"][0]["body"] == SECRET
