"""Maintainable-unit inventory (spec §3.1, §5.1, §5.4)."""
import io

from sqlalchemy import func, select

from app.models import MaintainableUnit

SAMPLE = (
    "code,kind,name,floor,room_type,external_id\n"
    "204,guest_room,Room 204,2,KNGN,\n"
    "POOL-PUMP-1,equipment,Pool pump 1,,,\n"
    "LOBBY,common_area,Lobby,1,,pms-lobby\n"
)


def _base(fx):
    return f"/api/p/{fx.property_a.id}/maintainable-units"


def _import(client, fx, text: str):
    return client.post(f"{_base(fx)}/import",
                       data={"file": (io.BytesIO(text.encode()), "units.csv", "text/csv")},
                       content_type="multipart/form-data")


def test_create_list_and_patch(app, fx, login):
    admin = login("admin@hvh.test")
    res = admin.post(_base(fx), json={"kind": "guest_room", "code": " 204 ", "name": "Room 204",
                                      "floor": 2, "roomType": "KNGN"})
    assert res.status_code == 201, res.get_json()
    unit = res.get_json()
    assert unit["code"] == "204" and unit["source"] == "manual" and unit["active"] is True

    rows = login("agent@hvh.test").get(f"{_base(fx)}?kind=guest_room").get_json()
    assert [r["id"] for r in rows] == [unit["id"]]
    assert login("agent@hvh.test").get(f"{_base(fx)}?kind=equipment").get_json() == []
    assert login("agent@hvh.test").get(f"{_base(fx)}?q=room+2").get_json()[0]["id"] == unit["id"]

    res = admin.patch(f"{_base(fx)}/{unit['id']}", json={"active": False, "notes": "Out of order"})
    assert res.status_code == 200 and res.get_json()["active"] is False
    assert login("agent@hvh.test").get(f"{_base(fx)}?active=true").get_json() == []


def test_duplicate_code_is_a_409_on_create_and_patch(app, fx, login):
    admin = login("admin@hvh.test")
    a = admin.post(_base(fx), json={"kind": "guest_room", "code": "204", "name": "A"}).get_json()
    admin.post(_base(fx), json={"kind": "guest_room", "code": "205", "name": "B"})
    assert admin.post(_base(fx), json={"kind": "equipment", "code": "204",
                                       "name": "C"}).status_code == 409
    assert admin.patch(f"{_base(fx)}/{a['id']}", json={"code": "205"}).status_code == 409


def test_writes_require_manage_admin_and_reads_are_open_to_staff(app, fx, login):
    for c in (login("engineer@hvh.test"), login("manager@hvh.test")):
        assert c.get(_base(fx)).status_code == 200
        assert c.post(_base(fx), json={"kind": "guest_room", "code": "1", "name": "x"}) \
            .status_code == 403
        assert _import(c, fx, SAMPLE).status_code == 403


def test_natural_sort_puts_numeric_codes_first_in_numeric_order(app, fx, login):
    admin = login("admin@hvh.test")
    for code in ("1001", "205", "BOILER-1", "99", "ANNEX"):
        admin.post(_base(fx), json={"kind": "equipment", "code": code, "name": code})
    codes = [r["code"] for r in admin.get(f"{_base(fx)}?kind=equipment").get_json()]
    assert codes == ["99", "205", "1001", "ANNEX", "BOILER-1"]


def test_import_creates_then_updates_idempotently(app, fx, login, database):
    admin = login("admin@hvh.test")
    res = _import(admin, fx, SAMPLE)
    assert res.status_code == 200, res.get_json()
    assert res.get_json() == {"created": 3, "updated": 0, "errors": []}
    with database.session() as db:
        pump = db.scalar(select(MaintainableUnit).where(MaintainableUnit.code == "POOL-PUMP-1"))
        assert pump.kind.value == "equipment" and pump.floor is None and pump.source.value == "csv"
        lobby = db.scalar(select(MaintainableUnit).where(MaintainableUnit.code == "LOBBY"))
        assert lobby.external_id == "pms-lobby"

    res = _import(admin, fx, SAMPLE.replace("Room 204", "Room 204 (renamed)"))
    assert res.get_json() == {"created": 0, "updated": 3, "errors": []}
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(MaintainableUnit)) == 3
        assert db.scalar(select(MaintainableUnit.name)
                         .where(MaintainableUnit.code == "204")) == "Room 204 (renamed)"


def test_import_with_one_bad_row_writes_nothing_and_names_the_line(app, fx, login, database):
    admin = login("admin@hvh.test")
    bad = SAMPLE.replace("equipment,Pool pump 1", "gadget,Pool pump 1")
    res = _import(admin, fx, bad)
    assert res.status_code == 422
    # The report rides in the standard error envelope so the client's ApiError.details is
    # the report itself (web/src/api/client.ts reads only `body.error`).
    body = res.get_json()["error"]
    assert body["code"] == "IMPORT_REJECTED"
    report = body["details"]
    assert report["created"] == 0 and report["updated"] == 0
    assert report["errors"][0]["line"] == 3 and report["errors"][0]["field"] == "kind"
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(MaintainableUnit)) == 0


def test_import_rejects_duplicate_codes_in_the_file_and_a_wrong_header(app, fx, login):
    admin = login("admin@hvh.test")
    dup = SAMPLE + "204,guest_room,Again,2,,\n"
    report = _import(admin, fx, dup).get_json()["error"]["details"]
    assert [e["line"] for e in report["errors"]] == [5]
    assert "duplicate" in report["errors"][0]["message"]

    res = _import(admin, fx, "code,kind,name\n204,guest_room,Room\n")
    report = res.get_json()["error"]["details"]
    assert report["errors"][0]["line"] == 1 and report["errors"][0]["field"] == "header"


def test_import_requires_a_file_and_caps_its_size(app, fx, login):
    admin = login("admin@hvh.test")
    res = admin.post(f"{_base(fx)}/import", data={}, content_type="multipart/form-data")
    assert res.status_code == 400 and res.get_json()["error"]["details"] == {"file": "required"}
    huge = "code,kind,name,floor,room_type,external_id\n" + ("x" * 1024 * 1024) + "\n"
    res = _import(admin, fx, huge)
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"file": "file_too_large"}


def test_units_are_property_scoped(app, fx, login):
    admin_a = login("admin@hvh.test")
    unit = admin_a.post(_base(fx), json={"kind": "guest_room", "code": "204",
                                         "name": "Room 204"}).get_json()
    admin_b = login("admin@lsi.test")
    base_b = f"/api/p/{fx.property_b.id}/maintainable-units"
    assert admin_b.get(base_b).get_json() == []
    assert admin_b.patch(f"{base_b}/{unit['id']}", json={"name": "x"}).status_code == 404
