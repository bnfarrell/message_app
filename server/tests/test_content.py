from sqlalchemy import select

from app.models import Conversation, DigitalAsset
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def test_quick_reply_crud_search_and_render(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/quick-replies"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"shortcut": "/wifi", "title": "WiFi", "body": "Hi {{guest_first_name}}, WiFi is Harbourview-Guest, room {{room_number}}."})
    assert r.status_code == 201
    qr = r.get_json()
    admin.post(base, json={"shortcut": "/towels", "title": "Towels", "body": "Towels on the way to {{room_number}}.",
                           "departmentId": fx.dept_housekeeping.id})
    dup = admin.post(base, json={"shortcut": "/wifi", "title": "x", "body": "y"})
    assert dup.status_code == 409
    agent = login("agent@hvh.test")
    assert [x["shortcut"] for x in agent.get(base + "?q=wif").get_json()] == ["/wifi"]
    assert [x["shortcut"] for x in agent.get(base + "?q=on the way").get_json()] == ["/towels"]
    assert agent.post(base, json={"shortcut": "/x", "title": "x", "body": "y"}).status_code == 403
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    rendered = agent.post(f"{base}/{qr['id']}/render", json={"conversationId": cid}).get_json()
    assert rendered["body"] == "Hi Sarah, WiFi is Harbourview-Guest, room 412."
    assert rendered["segments"] == 1
    assert agent.get(base).get_json()[0]["usageCount"] == 1  # sorted by usage desc
    assert admin.patch(f"{base}/{qr['id']}", json={"active": False}).status_code == 200
    assert [x["shortcut"] for x in agent.get(base).get_json()] == ["/towels"]
    assert len(admin.get(base + "?includeInactive=true").get_json()) == 2
    assert admin.delete(f"{base}/{qr['id']}").status_code == 204


def test_assets_crud_short_link_and_send_appends_link(app, fx, client, database, login, worker):
    base = f"/api/p/{fx.property_a.id}/assets"
    admin = login("admin@hvh.test")
    a = admin.post(base, json={"name": "WiFi card", "type": "link", "url": "https://example.test/wifi.pdf",
                               "category": "Connectivity"}).get_json()
    assert len(a["shortCode"]) == 6
    r = client.get(f"/a/{a['shortCode']}")
    assert r.status_code == 302 and r.headers["Location"] == "https://example.test/wifi.pdf"
    assert client.get("/a/nope00").status_code == 404
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "wifi?")
    cid = _cid(database, fx.guest_inhouse_a.id)
    agent = login("agent@hvh.test")
    m = agent.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                   json={"body": "Here you go:", "digitalAssetId": a["id"]}).get_json()
    assert m["body"] == f"Here you go: /a/{a['shortCode']}" and m["digitalAssetId"] == a["id"]
    with database.session() as db:
        assert db.get(DigitalAsset, a["id"]).send_count == 1
    assert admin.patch(f"{base}/{a['id']}", json={"name": "WiFi card v2"}).get_json()["name"] == "WiFi card v2"
    assert admin.delete(f"{base}/{a['id']}").status_code == 204
    assert client.get(f"/a/{a['shortCode']}").status_code == 404


def test_resolution_categories_tree(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/resolution-categories"
    admin = login("admin@hvh.test")
    parent = admin.post(base, json={"name": "Maintenance"}).get_json()
    child = admin.post(base, json={"name": "HVAC", "parentId": parent["id"]}).get_json()
    tree = admin.get(base).get_json()
    assert tree[0]["name"] == "Maintenance" and tree[0]["children"][0]["id"] == child["id"]
    assert admin.patch(f"{base}/{child['id']}", json={"name": "HVAC / AC"}).get_json()["name"] == "HVAC / AC"
    assert admin.delete(f"{base}/{parent['id']}").status_code == 409  # has children
    assert admin.delete(f"{base}/{child['id']}").status_code == 204
    assert admin.delete(f"{base}/{parent['id']}").status_code == 204
