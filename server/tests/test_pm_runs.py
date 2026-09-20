"""PM runs (spec §3.6–3.8, §4.2, §4.3)."""
import io

from sqlalchemy import select

from app.models import Notification, WorkOrder

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"
GIF = b"GIF89a" + b"\x00" * 40

ITEMS = [
    {"label": "HVAC filter replaced", "itemType": "checkbox"},
    {"label": "Tap hot-water temperature", "itemType": "number", "unit": "°F",
     "minValue": 100, "maxValue": 120},
    {"label": "Caulk condition", "itemType": "text", "required": False},
    {"label": "Bathroom fan photo", "itemType": "photo"},
]


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def setup_sweep(admin, fx, codes=("204", "205")):
    """A guest-room quarterly template (Engineering) and the given rooms. Returns
    (template_id, {code: unit_id})."""
    units = {}
    for code in codes:
        units[code] = admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                                 json={"kind": "guest_room", "code": code, "name": f"Room {code}",
                                       "floor": int(code[0])}).get_json()["id"]
    t = admin.post(_pm(fx, "/templates"), json={
        "name": "Guest Room Quarterly", "mode": "sweep", "unitKind": "guest_room",
        "cadence": "quarterly", "departmentId": fx.dept_engineering.id, "items": ITEMS})
    assert t.status_code == 201, t.get_json()
    return t.get_json()["id"], units


def start(client, fx, template_id, unit_id):
    res = client.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": unit_id})
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def answer_by_label(run, label):
    item = next(i for i in run["items"] if i["label"] == label)
    return next(a for a in run["answers"] if a["itemId"] == item["id"]), item


def upload(client, fx, run_id, data, item_id=None, filename="p.png", content_type="image/png"):
    form = {"photo": (io.BytesIO(data), filename, content_type)}
    if item_id:
        form["itemId"] = item_id
    return client.post(_pm(fx, f"/runs/{run_id}/photos"), data=form,
                       content_type="multipart/form-data")


def test_start_pre_creates_answers_and_refuses_a_second_run_in_the_cycle(app, fx, login, events):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    assert run["status"] == "in_progress" and run["startedByName"] == "Eli Engineer"
    assert run["unitCode"] == "204" and run["cycleId"]
    assert len(run["answers"]) == 4 and all(a["answeredAt"] is None for a in run["answers"])
    required = [i["id"] for i in run["items"] if i["required"]]
    assert run["missingRequired"] == required and len(required) == 3

    res = eng.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": units["204"]})
    assert res.status_code == 409 and res.get_json()["error"]["details"] == {"runId": run["id"]}
    res = login("supervisor@hvh.test").post(_pm(fx, "/runs"),
                                            json={"templateId": template_id,
                                                  "unitId": units["204"]})
    assert res.status_code == 409
    assert any(e.type == "pm.run.changed" and e.payload["id"] == run["id"] for e in events)


def test_start_refuses_a_unit_outside_the_templates_scope(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    pump = admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                      json={"kind": "equipment", "code": "PUMP", "name": "Pump"}).get_json()["id"]
    admin.patch(f"/api/p/{fx.property_a.id}/maintainable-units/{units['205']}",
                json={"active": False})
    eng = login("engineer@hvh.test")
    for unit_id in (pump, units["205"]):
        res = eng.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": unit_id})
        assert res.status_code == 400, unit_id


def test_answers_save_by_type_and_flag_out_of_range(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    path = _pm(fx, f"/runs/{run['id']}/answers/{temp['id']}")

    res = eng.patch(path, json={"numberValue": 122})
    assert res.status_code == 200, res.get_json()
    saved, _ = answer_by_label(res.get_json(), "Tap hot-water temperature")
    assert saved["numberValue"] == 122.0 and saved["outOfRange"] is True
    assert saved["answeredAt"] is not None

    saved, _ = answer_by_label(eng.patch(path, json={"numberValue": 110}).get_json(),
                               "Tap hot-water temperature")
    assert saved["outOfRange"] is False

    # Wrong value column for the type, and a photo item cannot be PATCHed at all.
    assert eng.patch(path, json={"boolValue": True}).status_code == 400
    assert eng.patch(path, json={"numberValue": 1, "textValue": "x"}).status_code == 400
    photo, _ = answer_by_label(run, "Bathroom fan photo")
    assert eng.patch(_pm(fx, f"/runs/{run['id']}/answers/{photo['id']}"),
                     json={"textValue": "x"}).status_code == 400

    # Clearing a value un-answers it.
    saved, _ = answer_by_label(eng.patch(path, json={"numberValue": None}).get_json(),
                               "Tap hot-water temperature")
    assert saved["numberValue"] is None and saved["answeredAt"] is None

    text, _ = answer_by_label(run, "Caulk condition")
    saved, _ = answer_by_label(
        eng.patch(_pm(fx, f"/runs/{run['id']}/answers/{text['id']}"),
                  json={"textValue": "  Fine  "}).get_json(), "Caulk condition")
    assert saved["textValue"] == "Fine"


def test_complete_requires_every_required_item_then_raises_work_orders(app, fx, login, database,
                                                                        events):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    run_path = _pm(fx, f"/runs/{run['id']}")

    res = eng.post(f"{run_path}/complete")
    assert res.status_code == 400
    assert len(res.get_json()["error"]["details"]["missingItemIds"]) == 3

    hvac, _ = answer_by_label(run, "HVAC filter replaced")
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    _, fan_item = answer_by_label(run, "Bathroom fan photo")
    # A required checkbox left unticked is still missing.
    eng.patch(f"{run_path}/answers/{hvac['id']}", json={"boolValue": False})
    eng.patch(f"{run_path}/answers/{temp['id']}", json={"numberValue": 122})
    assert upload(eng, fx, run["id"], PNG, item_id=fan_item["id"]).status_code == 201
    res = eng.post(f"{run_path}/complete")
    assert res.status_code == 400 and res.get_json()["error"]["details"]["missingItemIds"] == \
        [hvac["itemId"]]
    eng.patch(f"{run_path}/answers/{hvac['id']}", json={"boolValue": True})
    assert eng.get(run_path).get_json()["missingRequired"] == []

    res = eng.post(f"{run_path}/complete")
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["status"] == "completed" and res.get_json()["completedAt"]

    with database.session() as db:
        wos = db.scalars(select(WorkOrder).where(WorkOrder.property_id == fx.property_a.id)).all()
        assert len(wos) == 1
        wo = wos[0]
        assert wo.type.value == "maintenance" and wo.priority.value == "high"
        assert wo.location_ref == "204" and wo.department_id == fx.dept_engineering.id
        assert wo.title == "Tap hot-water temperature 122°F out of range (100–120) — Room 204"
        notes = db.scalars(select(Notification).where(
            Notification.type == "pm.out_of_range")).all()
        assert [n.user_id for n in notes] == [fx.supervisor_a.id]
        assert notes[0].entity_id == wo.id

    # Locked after completion.
    assert eng.patch(f"{run_path}/answers/{temp['id']}", json={"numberValue": 1}) \
        .status_code == 409
    assert upload(eng, fx, run["id"], PNG).status_code == 409
    assert eng.post(f"{run_path}/complete").status_code == 409
    assert sum(1 for e in events if e.type == "pm.run.changed") >= 2


def test_an_in_range_completion_raises_nothing(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    run_path = _pm(fx, f"/runs/{run['id']}")
    hvac, _ = answer_by_label(run, "HVAC filter replaced")
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    _, fan_item = answer_by_label(run, "Bathroom fan photo")
    eng.patch(f"{run_path}/answers/{hvac['id']}", json={"boolValue": True})
    eng.patch(f"{run_path}/answers/{temp['id']}", json={"numberValue": 110})
    upload(eng, fx, run["id"], PNG, item_id=fan_item["id"])
    assert eng.post(f"{run_path}/complete").status_code == 200
    with database.session() as db:
        assert db.scalar(select(WorkOrder.id)) is None


def test_photos_validate_and_round_trip(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    _, hvac_item = answer_by_label(run, "HVAC filter replaced")

    assert upload(eng, fx, run["id"], GIF).status_code == 400
    assert upload(eng, fx, run["id"], b"x" * (8 * 1024 * 1024 + 1)).status_code == 400
    assert upload(eng, fx, run["id"], PNG, item_id=hvac_item["id"]).status_code == 400

    res = upload(eng, fx, run["id"], PNG)  # general evidence, no item
    assert res.status_code == 201
    photo = res.get_json()["photos"][0]
    assert photo["itemId"] is None and photo["byteSize"] == len(PNG)
    served = eng.get(photo["url"])
    assert served.status_code == 200 and served.data == PNG
    assert served.headers["Content-Type"] == "image/png"
    assert login("admin@lsi.test").get(photo["url"].replace(fx.property_a.id, fx.property_b.id)) \
        .status_code == 404


def test_perform_pm_gates_starting_and_runs_are_property_scoped(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    res = login("agent@hvh.test").post(_pm(fx, "/runs"),
                                       json={"templateId": template_id, "unitId": units["204"]})
    assert res.status_code == 403
    run = start(login("engineer@hvh.test"), fx, template_id, units["204"])
    assert login("agent@hvh.test").get(_pm(fx, f"/runs/{run['id']}")).status_code == 200
    assert login("admin@lsi.test").get(f"/api/p/{fx.property_b.id}/pm/runs/{run['id']}") \
        .status_code == 404
