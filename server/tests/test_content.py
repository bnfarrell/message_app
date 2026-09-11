from sqlalchemy import select

from app.models import Conversation, DigitalAsset
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def test_quick_reply_crud_search_and_render(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/quick-replies"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"shortcut": "/wifi", "title": "WiFi",
                               "body": "Hi {{guest_first_name}}, WiFi is Harbourview-Guest, "
                                       "room {{room_number}}."})
    assert r.status_code == 201
    qr = r.get_json()
    admin.post(base, json={"shortcut": "/towels", "title": "Towels",
                           "body": "Towels on the way to {{room_number}}.",
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
    renamed = admin.patch(f"{base}/{a['id']}", json={"name": "WiFi card v2"})
    assert renamed.get_json()["name"] == "WiFi card v2"
    assert admin.delete(f"{base}/{a['id']}").status_code == 204
    assert client.get(f"/a/{a['shortCode']}").status_code == 404


def test_resolution_categories_tree(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/resolution-categories"
    admin = login("admin@hvh.test")
    parent = admin.post(base, json={"name": "Maintenance"}).get_json()
    child = admin.post(base, json={"name": "HVAC", "parentId": parent["id"]}).get_json()
    tree = admin.get(base).get_json()
    assert tree[0]["name"] == "Maintenance" and tree[0]["children"][0]["id"] == child["id"]
    renamed = admin.patch(f"{base}/{child['id']}", json={"name": "HVAC / AC"})
    assert renamed.get_json()["name"] == "HVAC / AC"
    assert admin.delete(f"{base}/{parent['id']}").status_code == 409  # has children
    assert admin.delete(f"{base}/{child['id']}").status_code == 204
    assert admin.delete(f"{base}/{parent['id']}").status_code == 204


def test_render_quick_reply_respects_viewer_scope(app, fx, client, database, login):
    """A dept_staff caller must not be able to render a quick reply against a conversation outside
    their department — the same viewer check that gates GET/PATCH/notes/messages on conversations
    (see test_dept_staff_sees_only_their_department_or_own_conversations) must also gate render."""
    base = f"/api/p/{fx.property_a.id}/quick-replies"
    admin = login("admin@hvh.test")
    qr = admin.post(base, json={"shortcut": "/ac", "title": "AC", "body": "On it."}).get_json()
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_nostay_a.id)  # unassigned: invisible to any dept_staff
    eng = login("engineer@hvh.test")
    assert eng.post(f"{base}/{qr['id']}/render", json={"conversationId": cid}).status_code == 403


def test_assets_require_manage_admin(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/assets"
    admin = login("admin@hvh.test")
    a = admin.post(base, json={"name": "Map", "type": "map", "url": "https://example.test/map.pdf"}).get_json()
    agent = login("agent@hvh.test")
    resp = agent.post(base, json={"name": "x", "type": "link", "url": "https://example.test/x"})
    assert resp.status_code == 403
    assert agent.patch(f"{base}/{a['id']}", json={"name": "y"}).status_code == 403
    assert agent.delete(f"{base}/{a['id']}").status_code == 403


def test_resolution_categories_require_manage_admin(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/resolution-categories"
    admin = login("admin@hvh.test")
    c = admin.post(base, json={"name": "Plumbing"}).get_json()
    agent = login("agent@hvh.test")
    assert agent.post(base, json={"name": "x"}).status_code == 403
    assert agent.patch(f"{base}/{c['id']}", json={"name": "y"}).status_code == 403
    assert agent.delete(f"{base}/{c['id']}").status_code == 403


def test_resolution_category_delete_blocked_by_conversation_reference(app, fx, client, database,
                                                                       login):
    """A category still referenced by a conversation's resolution_category_id (FK, no ondelete)
    must be rejected with a clean 409, not an unhandled IntegrityError/500."""
    base = f"/api/p/{fx.property_a.id}/resolution-categories"
    admin = login("admin@hvh.test")
    cat = admin.post(base, json={"name": "Noise complaint"}).get_json()
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "loud neighbors")
    cid = _cid(database, fx.guest_inhouse_a.id)
    resp = admin.patch(f"/api/p/{fx.property_a.id}/conversations/{cid}",
                       json={"status": "archived", "resolutionCategoryId": cat["id"]})
    assert resp.status_code == 200
    assert admin.delete(f"{base}/{cat['id']}").status_code == 409


def test_quick_reply_locale_is_patchable(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/quick-replies"
    admin = login("admin@hvh.test")
    qr = admin.post(base, json={"shortcut": "/bienvenue", "title": "Welcome",
                                "body": "Bonjour {{guest_first_name}}."}).get_json()
    assert qr["locale"] == "en"
    patched = admin.patch(f"{base}/{qr['id']}", json={"locale": "fr-CA"})
    assert patched.status_code == 200
    body = patched.get_json()
    assert body["locale"] == "fr-CA"
    assert (body["shortcut"], body["title"], body["body"], body["active"]) == (
        qr["shortcut"], qr["title"], qr["body"], qr["active"])
    assert admin.get(base).get_json()[0]["locale"] == "fr-CA"  # persisted
    # the column is String(8); an over-long value must not reach the database
    assert admin.patch(f"{base}/{qr['id']}", json={"locale": "x" * 9}).status_code == 400


def test_quick_reply_variables_endpoint_is_the_authoritative_list(app, fx, login):
    from app.domain.quick_replies import VARIABLES

    res = login("agent@hvh.test").get(f"/api/p/{fx.property_a.id}/quick-replies/variables")
    assert res.status_code == 200
    assert res.get_json() == list(VARIABLES)
    assert "property_name" in res.get_json()  # the mockup omits this chip; the server is the truth


def test_preview_falls_back_without_a_conversation(app, fx, login):
    from app.domain.quick_replies import FALLBACKS

    url = f"/api/p/{fx.property_a.id}/quick-replies/preview"
    body = "Hi {{guest_first_name}}, room {{room_number}} — see {{agent_first_name}}."
    res = login("admin@hvh.test").post(url, json={"body": body})
    assert res.status_code == 200, res.get_json()
    out = res.get_json()
    assert out["body"] == (f"Hi {FALLBACKS['guest_first_name']}, "
                           f"room {FALLBACKS['room_number']} — "
                           f"see {FALLBACKS['agent_first_name']}.")
    assert out["characters"] == len(out["body"])


def test_preview_uses_real_guest_data_with_a_conversation(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    url = f"/api/p/{fx.property_a.id}/quick-replies/preview"
    out = login("admin@hvh.test").post(url, json={
        "body": "Hi {{guest_first_name}} in {{room_number}} at {{property_name}}.",
        "conversationId": cid}).get_json()
    assert out["body"] == "Hi Sarah in 412 at Harbourview Hotel."


def test_preview_does_not_touch_usage_count(app, fx, database, login):
    """The regression that made /render unusable as a preview: the admin table shows a "Uses"
    column, and previewing must not inflate it."""
    from app.models import QuickReply

    base = f"/api/p/{fx.property_a.id}/quick-replies"
    admin = login("admin@hvh.test")
    qr = admin.post(base, json={"shortcut": "/spa", "title": "Spa",
                                "body": "The spa closes at 8."}).get_json()
    with database.session() as db:
        before = db.get(QuickReply, qr["id"]).usage_count
    for _ in range(3):
        res = admin.post(f"{base}/preview", json={"body": "The spa closes at 8."})
        assert res.status_code == 200
    with database.session() as db:
        assert db.get(QuickReply, qr["id"]).usage_count == before == 0


def test_preview_capability_differs_from_render(app, fx, login):
    """`corporate` holds manage_admin but not `reply`, so it can open the admin screen and must be
    able to drive the preview pane on it — the second reason /render cannot serve this."""
    url = f"/api/p/{fx.property_a.id}/quick-replies/preview"
    assert login("corporate@hvh.test").post(url, json={"body": "hello"}).status_code == 200
    for email in ("agent@hvh.test", "manager@hvh.test", "engineer@hvh.test"):
        assert login(email).post(url, json={"body": "hello"}).status_code == 403


def test_preview_counts_segments_the_same_way_the_sender_does(app, fx, login):
    from app.domain.sms import segment_count

    url = f"/api/p/{fx.property_a.id}/quick-replies/preview"
    admin = login("admin@hvh.test")
    for body in ("a" * 160, "a" * 161, "café " * 20, "😀" + "a" * 69):
        out = admin.post(url, json={"body": body}).get_json()
        assert (out["segments"], out["characters"]) == (segment_count(body), len(body)), body
    assert admin.post(url, json={"body": ""}).status_code == 400


def test_patching_a_not_null_field_to_null_is_a_400_not_a_500(app, fx, login):
    """Ruling D82. A PATCH schema declares every field `T | None = None` so `exclude_unset` can
    tell absent from present, which makes an explicit null indistinguishable at the edge. Before
    the shared `patch_changes` guard these reached the NOT NULL constraint: an unhandled
    IntegrityError (500) everywhere, except on quick replies, where the nested flush's
    `except IntegrityError` blamed the shortcut and returned 409 "Shortcut None is already in use".
    """
    admin = login("admin@hvh.test")
    base = f"/api/p/{fx.property_a.id}"
    qr = admin.post(f"{base}/quick-replies", json={"shortcut": "/null", "title": "T",
                                                   "body": "B"}).get_json()
    cat = admin.post(f"{base}/resolution-categories", json={"name": "Maintenance"}).get_json()
    asset = admin.post(f"{base}/assets", json={"name": "Menu",
                                               "url": "https://example.test/m.pdf"}).get_json()
    cases = [
        (f"{base}/quick-replies/{qr['id']}", "locale"),
        (f"{base}/quick-replies/{qr['id']}", "shortcut"),
        (f"{base}/quick-replies/{qr['id']}", "body"),
        (f"{base}/resolution-categories/{cat['id']}", "name"),
        (f"{base}/resolution-categories/{cat['id']}", "active"),
        (f"{base}/assets/{asset['id']}", "name"),
        (f"{base}/assets/{asset['id']}", "url"),
    ]
    for url, field in cases:
        res = admin.patch(url, json={field: None})
        assert res.status_code == 400, (url, field, res.status_code, res.get_json())
        body = res.get_json()["error"]
        assert body["code"] == "VALIDATION_FAILED" and field in body["message"], (url, field)

    # the nullable neighbours on the same models must still be clearable
    assert admin.patch(f"{base}/quick-replies/{qr['id']}",
                       json={"departmentId": None, "category": None}).status_code == 200
    assert admin.patch(f"{base}/resolution-categories/{cat['id']}",
                       json={"parentId": None}).status_code == 200
    assert admin.patch(f"{base}/assets/{asset['id']}",
                       json={"description": None}).status_code == 200
