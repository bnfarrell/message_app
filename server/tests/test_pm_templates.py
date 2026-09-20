"""PM templates (spec §3.2–3.4, §4.5, §5.2, §7.1)."""
from sqlalchemy import select

from app import clock
from app.models import PmCycle, PmRun, PmTemplateItem
from app.schemas.enums import PmRunStatus

ITEMS = [
    {"label": "HVAC filter replaced", "itemType": "checkbox"},
    {"label": "Tap hot-water temperature", "itemType": "number", "unit": "°F",
     "minValue": 100, "maxValue": 120},
    {"label": "Caulk condition", "itemType": "text", "required": False},
    {"label": "Bathroom fan photo", "itemType": "photo"},
]


def _base(fx):
    return f"/api/p/{fx.property_a.id}/pm/templates"


def _sweep_body(**over):
    return {"name": "Guest Room Quarterly", "mode": "sweep", "unitKind": "guest_room",
            "cadence": "quarterly", "items": ITEMS} | over


def _unit(client, fx, code, kind="equipment"):
    return client.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                       json={"kind": kind, "code": code, "name": code}).get_json()["id"]


def test_create_sweep_opens_todays_cycle_and_orders_items(app, fx, login, database):
    admin = login("admin@hvh.test")
    res = admin.post(_base(fx), json=_sweep_body(departmentId=fx.dept_engineering.id))
    assert res.status_code == 201, res.get_json()
    t = res.get_json()
    assert [i["position"] for i in t["items"]] == [0, 1, 2, 3]
    assert t["items"][1]["minValue"] == 100.0 and t["items"][2]["required"] is False
    assert t["hasRuns"] is False
    with database.session() as db:
        cycle = db.scalar(select(PmCycle).where(PmCycle.template_id == t["id"]))
        assert cycle is not None and cycle.ordinal == 3  # frozen clock: 2026-09-10, Q3
    assert login("agent@hvh.test").get(_base(fx)).get_json()[0]["id"] == t["id"]


def test_one_active_sweep_per_kind(app, fx, login):
    admin = login("admin@hvh.test")
    assert admin.post(_base(fx), json=_sweep_body()).status_code == 201
    assert admin.post(_base(fx), json=_sweep_body(name="Another")).status_code == 409
    # A different kind is fine, and so is an inactive duplicate.
    assert admin.post(_base(fx), json=_sweep_body(unitKind="equipment")).status_code == 201
    assert admin.post(_base(fx), json=_sweep_body(active=False)).status_code == 201


def test_mode_fields_are_validated(app, fx, login):
    admin = login("admin@hvh.test")
    bad = [
        _sweep_body(rrule="FREQ=DAILY"),
        _sweep_body(cadence=None),
        {"name": "B", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3"},  # no dtstart
        {"name": "B", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3",
         "rruleDtstart": "2026-07-01", "cadence": "monthly"},
        {"name": "B", "mode": "scheduled", "rrule": "EVERY=THIRD;MOON",
         "rruleDtstart": "2026-07-01"},
    ]
    for body in bad:
        res = admin.post(_base(fx), json=body)
        assert res.status_code == 400, body


def test_sub_daily_rrule_frequencies_are_rejected(app, fx, login):
    admin = login("admin@hvh.test")
    for freq in ("SECONDLY", "MINUTELY", "HOURLY"):
        res = admin.post(_base(fx), json={
            "name": "Too fine", "mode": "scheduled", "rrule": f"FREQ={freq}",
            "rruleDtstart": "2026-07-01"})
        assert res.status_code == 400, freq
        assert res.get_json()["error"]["details"] == {"rrule": "frequency_too_fine"}
    res = admin.post(_base(fx), json={
        "name": "Daily is fine", "mode": "scheduled", "rrule": "FREQ=DAILY",
        "rruleDtstart": "2026-07-01", "items": ITEMS[:1]})
    assert res.status_code == 201, res.get_json()


def test_scheduled_template_targets_units_of_this_property_only(app, fx, login):
    admin = login("admin@hvh.test")
    boiler = _unit(admin, fx, "BOILER-1")
    other = login("admin@lsi.test").post(
        f"/api/p/{fx.property_b.id}/maintainable-units",
        json={"kind": "equipment", "code": "X", "name": "X"}).get_json()["id"]
    body = {"name": "Boiler inspection", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3",
            "rruleDtstart": "2026-07-01", "unitIds": [boiler], "items": ITEMS[:1]}
    res = admin.post(_base(fx), json=body)
    assert res.status_code == 201 and res.get_json()["unitIds"] == [boiler]
    assert admin.post(_base(fx), json=body | {"unitIds": [boiler, other]}).status_code == 400


def test_patch_soft_deletes_removed_items_and_keeps_answers_valid(app, fx, login, database):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    keep = t["items"][1]
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={"items": [
        {"id": keep["id"], "label": "Tap temperature", "itemType": "number", "unit": "°F",
         "minValue": 95, "maxValue": 125},
        {"label": "Smoke detector tested", "itemType": "checkbox"},
    ]})
    assert res.status_code == 200, res.get_json()
    out = res.get_json()
    assert [i["label"] for i in out["items"]] == ["Tap temperature", "Smoke detector tested"]
    assert out["items"][0]["id"] == keep["id"] and out["items"][0]["minValue"] == 95.0
    with database.session() as db:
        rows = db.scalars(select(PmTemplateItem).where(
            PmTemplateItem.template_id == t["id"])).all()
        assert len(rows) == 5, "nothing is hard-deleted"
        assert sorted(r.active for r in rows) == [False, False, False, True, True]


def test_patch_never_leaves_two_items_sharing_a_position(app, fx, login, database):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    keep = t["items"][1]
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={"items": [
        {"id": keep["id"], "label": keep["label"], "itemType": "number", "unit": "°F",
         "minValue": 100, "maxValue": 120},
        {"label": "Smoke detector tested", "itemType": "checkbox"},
    ]})
    assert res.status_code == 200, res.get_json()
    with database.session() as db:
        rows = db.scalars(select(PmTemplateItem).where(
            PmTemplateItem.template_id == t["id"])).all()
        positions = [r.position for r in rows]
        assert len(positions) == len(set(positions)), "no two items share a position"


def test_patch_rejects_duplicate_item_ids(app, fx, login):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    keep = t["items"][0]
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={"items": [
        {"id": keep["id"], "label": "First edit", "itemType": "checkbox"},
        {"id": keep["id"], "label": "Second edit", "itemType": "checkbox"},
    ]})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"items": "duplicate_item"}
    assert admin.get(_base(fx)).get_json()[0]["items"][0]["label"] == keep["label"]


def test_item_type_is_immutable_and_bounds_only_on_numbers(app, fx, login):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    checkbox = t["items"][0]
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={"items": [
        {"id": checkbox["id"], "label": checkbox["label"], "itemType": "text"}]})
    assert res.status_code == 400
    res = admin.post(_base(fx), json=_sweep_body(
        unitKind="equipment", items=[{"label": "x", "itemType": "checkbox", "minValue": 1}]))
    assert res.status_code == 400
    res = admin.post(_base(fx), json=_sweep_body(
        unitKind="equipment", items=[{"label": "x", "itemType": "number", "minValue": 5,
                                     "maxValue": 1}]))
    assert res.status_code == 400


def test_mode_cannot_change_once_the_template_has_runs(app, fx, login, database):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    unit = _unit(admin, fx, "204", kind="guest_room")
    with database.session() as db:
        db.add(PmRun(property_id=fx.property_a.id, template_id=t["id"], unit_id=unit,
                     status=PmRunStatus.in_progress, started_at=clock.now()))
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={
        "mode": "scheduled", "unitKind": None, "cadence": None,
        "rrule": "FREQ=MONTHLY", "rruleDtstart": "2026-07-01"})
    assert res.status_code == 409
    assert admin.get(_base(fx)).get_json()[0]["hasRuns"] is True


def test_writes_require_manage_admin(app, fx, login):
    for c in (login("supervisor@hvh.test"), login("manager@hvh.test")):
        assert c.get(_base(fx)).status_code == 200
        assert c.post(_base(fx), json=_sweep_body()).status_code == 403
