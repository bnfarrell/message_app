"""Checklist structure over HTTP (checklist structure spec §3): camelCase on the wire."""

TEMPLATE = {
    "name": "Night Audit", "schedule": "on_demand", "kind": "readings",
    "categories": [{"key": "a", "name": "Audit"}, {"key": "p", "name": "Payments"}],
    "items": [{"label": "Night audit run", "itemType": "checkbox", "categoryKey": "a"},
              {"label": "Card batch closed", "itemType": "checkbox", "categoryKey": "p"},
              {"label": "Notes", "itemType": "text", "required": False}],
}


def _ck(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/checklists{rest}"


def _create(login, fx, **over):
    body = {**TEMPLATE, "departmentId": fx.dept_front_desk.id, **over}
    res = login("admin@hvh.test").post(_ck(fx, "/templates"), json=body)
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def test_categories_and_kind_round_trip(app, fx, login):
    created = _create(login, fx)
    assert created["kind"] == "readings"
    assert [(c["name"], c["position"]) for c in created["categories"]] == [("Audit", 0),
                                                                          ("Payments", 1)]
    audit, pay = (c["id"] for c in created["categories"])
    assert [i["categoryId"] for i in created["items"]] == [audit, pay, None]
    listed = login("agent@hvh.test").get(_ck(fx, "/templates")).get_json()
    assert listed[0]["categories"] == created["categories"]


def test_patch_with_categories_keyed_by_saved_id(app, fx, login):
    created = _create(login, fx)
    audit, pay = created["categories"]
    items = [{"id": i["id"], "label": i["label"], "itemType": i["itemType"],
              "required": i["required"], "categoryKey": pay["id"]} for i in created["items"]]
    res = login("admin@hvh.test").patch(_ck(fx, f"/templates/{created['id']}"), json={
        "categories": [{"key": pay["id"], "id": pay["id"], "name": "Payments"}],
        "items": items})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert [c["name"] for c in body["categories"]] == ["Payments"]
    assert {i["categoryId"] for i in body["items"]} == {pay["id"]}


def test_an_unknown_category_key_names_the_items_field(app, fx, login):
    res = login("admin@hvh.test").post(_ck(fx, "/templates"), json={
        **TEMPLATE, "departmentId": fx.dept_front_desk.id,
        "items": [{"label": "x", "itemType": "checkbox", "categoryKey": "zzz"}]})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"items": "unknown_category"}


def test_more_than_thirty_categories_is_a_400(app, fx, login):
    res = login("admin@hvh.test").post(_ck(fx, "/templates"), json={
        **TEMPLATE, "departmentId": fx.dept_front_desk.id,
        "categories": [{"key": f"k{n}", "name": f"C{n}"} for n in range(31)]})
    assert res.status_code == 400


def test_pm_items_still_refuse_a_category_key(app, fx, login):
    """PM's TemplateItemIn is not modified (spec §3.1): it still rejects unknown fields."""
    res = login("admin@hvh.test").post(f"/api/p/{fx.property_a.id}/pm/templates", json={
        "name": "Quarterly", "mode": "sweep", "unitKind": "guest_room", "cadence": "quarterly",
        "items": [{"label": "Filter", "itemType": "checkbox", "categoryKey": "a"}]})
    assert res.status_code == 400
