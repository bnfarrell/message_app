"""The log-templates HTTP surface (log templates spec §3)."""
import io
import json

from app.models import LogTemplate

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"

TEMPLATE = {
    "name": "Night Audit", "shift": "overnight",
    "fields": [{"label": "Arrivals actual", "fieldType": "integer"},
               {"label": "Occupancy", "fieldType": "percent"},
               {"label": "Notes", "fieldType": "long_text", "required": False}],
}


def _admin(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/log-templates{rest}"


def _entries(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/log-entries{rest}"


def _create(login, fx, **over):
    res = login("admin@hvh.test").post(_admin(fx), json={**TEMPLATE, **over})
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def test_admin_create_patch_and_list_round_trip(app, fx, login):
    admin = login("admin@hvh.test")
    created = _create(login, fx, audience=[{"type": "department", "id": fx.dept_front_desk.id}])
    assert [f["fieldType"] for f in created["fields"]] == ["integer", "percent", "long_text"]
    assert created["usedCount"] == 0
    occ = created["fields"][1]
    res = admin.patch(_admin(fx, f"/{created['id']}"), json={
        "active": False,
        "fields": [{"id": occ["id"], "label": "Occupancy %", "fieldType": "percent"}]})
    assert res.status_code == 200, res.get_json()
    listed = admin.get(_admin(fx)).get_json()
    assert [(t["name"], t["active"], [f["label"] for f in t["fields"]]) for t in listed] == [
        ("Night Audit", False, ["Occupancy %"])]


def test_patching_a_saved_fields_type_is_a_400(app, fx, login):
    created = _create(login, fx)
    occ = created["fields"][1]
    res = login("admin@hvh.test").patch(_admin(fx, f"/{created['id']}"), json={
        "fields": [{"id": occ["id"], "label": "Occupancy", "fieldType": "integer"}]})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"fields": "type_change"}


def test_capabilities(app, fx, login):
    created = _create(login, fx)
    for email in ("agent@hvh.test", "supervisor@hvh.test", "manager@hvh.test"):
        c = login(email)
        assert c.get(_admin(fx)).status_code == 403, email
        assert c.post(_admin(fx), json=TEMPLATE).status_code == 403, email
        assert c.patch(_admin(fx, f"/{created['id']}"), json={}).status_code == 403, email
        assert c.get(_entries(fx, "/templates")).status_code == 200, email
    assert login("corporate@hvh.test").post(_admin(fx), json=TEMPLATE).status_code == 201


def test_the_picker_route_is_not_mistaken_for_an_entry_id(app, fx, login):
    _create(login, fx)
    rows = login("agent@hvh.test").get(_entries(fx, "/templates")).get_json()
    assert [r["name"] for r in rows] == ["Night Audit"]


def test_post_a_templated_entry_over_json_and_read_it_back(app, fx, login):
    created = _create(login, fx)
    ids = [f["id"] for f in created["fields"]]
    agent = login("agent@hvh.test")
    res = agent.post(_entries(fx), json={
        "templateId": created["id"], "body": "Quiet.",
        "fieldValues": [{"fieldId": ids[0], "value": 38}, {"fieldId": ids[1], "value": "87"}]})
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["template"] == {"id": created["id"], "name": "Night Audit"}
    assert [(v["label"], v["numberValue"]) for v in body["fieldValues"]] == [
        ("Arrivals actual", 38.0), ("Occupancy", 87.0)]
    assert (body["body"], body["notes"]) == ("Arrivals actual: 38\nOccupancy: 87%\n\nQuiet.",
                                             "Quiet.")
    feed = agent.get(_entries(fx)).get_json()["entries"]
    assert feed[0]["fieldValues"] == body["fieldValues"]
    assert login("admin@hvh.test").get(_admin(fx)).get_json()[0]["usedCount"] == 1


def test_post_a_templated_entry_over_multipart_with_a_photo(app, fx, login):
    created = _create(login, fx)
    ids = [f["id"] for f in created["fields"]]
    res = login("agent@hvh.test").post(_entries(fx), data={
        "templateId": created["id"],
        "fieldValues": json.dumps([{"fieldId": ids[0], "value": "12"},
                                   {"fieldId": ids[1], "value": "90"}]),
        "photo": (io.BytesIO(PNG), "x.png", "image/png")}, content_type="multipart/form-data")
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["photoUrl"]
    assert len(res.get_json()["fieldValues"]) == 2


def test_a_bad_answer_names_its_field_in_the_400(app, fx, login):
    created = _create(login, fx)
    ids = [f["id"] for f in created["fields"]]
    res = login("agent@hvh.test").post(_entries(fx), json={
        "templateId": created["id"],
        "fieldValues": [{"fieldId": ids[0], "value": "12.5"}, {"fieldId": ids[1], "value": 140}]})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {ids[0]: "not_whole", ids[1]: "out_of_range"}


def test_a_non_audience_user_is_403_and_does_not_see_it(app, fx, login):
    created = _create(login, fx, audience=[{"type": "department", "id": fx.dept_front_desk.id}])
    ids = [f["id"] for f in created["fields"]]
    eli = login("engineer@hvh.test")
    assert eli.get(_entries(fx, "/templates")).get_json() == []
    res = eli.post(_entries(fx), json={
        "templateId": created["id"],
        "fieldValues": [{"fieldId": ids[0], "value": 1}, {"fieldId": ids[1], "value": 2}]})
    assert res.status_code == 403


def test_a_template_of_another_property_is_404(app, database, fx, login):
    with database.session() as db:
        b = LogTemplate(property_id=fx.property_b.id, name="B", position=0,
                        created_by_user_id=fx.admin_b.id)
        db.add(b)
        db.flush()
        tid = b.id
    admin = login("admin@hvh.test")
    assert admin.patch(_admin(fx, f"/{tid}"), json={"name": "x"}).status_code == 404
    assert admin.post(_entries(fx), json={"templateId": tid}).status_code == 404
