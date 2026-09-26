"""The housekeeping HTTP surface (spec §4.1, §4.2)."""
import io

from app.domain import hk_rooms
from app.schemas.enums import HkStatus
from tests.hk_helpers import make_rooms

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _hk(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/housekeeping{rest}"


def _rooms(database, fx, codes=("101", "102")):
    with database.session() as db:
        return {c: r.id for c, r in make_rooms(db, fx.property_a.id, codes=codes).items()}


def test_the_whole_loop_over_http(database, fx, login):
    rooms = _rooms(database, fx)
    desk, sup, hana = login("agent@hvh.test"), login("supervisor@hvh.test"), \
        login("housekeeper@hvh.test")
    assert desk.post(_hk(fx, f"/rooms/{rooms['101']}/mark-dirty"),
                     json={"note": "Spill"}).status_code == 200
    assert desk.post(_hk(fx, f"/rooms/{rooms['101']}/rush")).get_json()["rush"] is True
    res = sup.post(_hk(fx, "/assignments"),
                   json={"roomIds": [rooms["101"]], "housekeeperUserId": fx.housekeeper_a.id})
    assert res.status_code == 201, res.get_json()
    aid = res.get_json()[0]["id"]
    mine = hana.get(_hk(fx, "/my-rooms")).get_json()
    assert [r["code"] for r in mine] == ["101"]
    assert hana.post(_hk(fx, f"/assignments/{aid}/start")).get_json()["hkStatus"] \
        == "in_progress"
    up = hana.post(_hk(fx, f"/assignments/{aid}/photos"),
                   data={"photo": (io.BytesIO(PNG), "p.png", "image/png")},
                   content_type="multipart/form-data")
    assert up.status_code == 201, up.get_json()
    photo_url = up.get_json()["photos"][0]["url"]
    assert hana.post(_hk(fx, f"/assignments/{aid}/complete")).get_json()["hkStatus"] == "clean"
    queue = sup.get(_hk(fx, "/inspections")).get_json()
    assert [row["room"]["code"] for row in queue] == ["101"]
    img = desk.get(photo_url)
    assert img.status_code == 200 and img.data == PNG
    assert sup.post(_hk(fx, f"/assignments/{aid}/inspect"),
                    json={"result": "fail"}).status_code == 400
    passed = sup.post(_hk(fx, f"/assignments/{aid}/inspect"), json={"result": "pass"})
    assert passed.get_json()["hkStatus"] == "inspected" and passed.get_json()["rush"] is False


def test_front_desk_cannot_assign_inspect_or_perform(database, fx, login):
    rooms = _rooms(database, fx)
    desk = login("agent@hvh.test")
    assert desk.post(_hk(fx, "/assignments"), json={
        "roomIds": [rooms["101"]], "housekeeperUserId": fx.housekeeper_a.id}).status_code == 403
    assert desk.get(_hk(fx, "/inspections")).status_code == 403
    assert desk.get(_hk(fx, "/my-rooms")).status_code == 403
    assert desk.post(_hk(fx, f"/rooms/{rooms['101']}/status"),
                     json={"status": "out_of_order"}).status_code == 403
    assert desk.get(_hk(fx, "/board")).status_code == 200


def test_board_summary_agrees_with_the_tiles(database, fx, login):
    _rooms(database, fx, codes=("101", "102", "103"))
    body = login("corporate@hvh.test").get(_hk(fx, "/board")).get_json()
    assert len(body["rooms"]) == 3
    assert sum(body["summary"].values()) == 3 and body["summary"]["inspected"] == 3


def test_assigning_to_engineering_is_a_400(database, fx, login):
    rooms = _rooms(database, fx)
    with database.session() as db:
        hk_rooms.get(db, fx.property_a.id, rooms["101"]).hk_status = HkStatus.dirty
    res = login("supervisor@hvh.test").post(_hk(fx, "/assignments"), json={
        "roomIds": [rooms["101"]], "housekeeperUserId": fx.engineer_a.id})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"housekeeperUserId": "not_housekeeping"}


def test_rooms_of_another_property_are_404_not_leaked(database, fx, login):
    with database.session() as db:
        other = make_rooms(db, fx.property_b.id, codes=("101",))["101"].id
    assert login("admin@hvh.test").get(_hk(fx, f"/rooms/{other}")).status_code == 404


def test_session_carries_the_department_type(fx, login):
    body = login("housekeeper@hvh.test").get("/api/auth/me").get_json()
    assert body["memberships"][0]["departmentType"] == "housekeeping"


def test_supervisor_self_assign_starts_a_dirty_unassigned_room(database, fx, login):
    rooms = _rooms(database, fx)
    with database.session() as db:
        hk_rooms.get(db, fx.property_a.id, rooms["101"]).hk_status = HkStatus.dirty
    res = login("supervisor@hvh.test").post(_hk(fx, f"/rooms/{rooms['101']}/self-assign-start"))
    assert res.status_code == 200
    assert res.get_json()["hkStatus"] == "in_progress"


def test_supervisor_unassigns_an_unstarted_assignment(database, fx, login):
    rooms = _rooms(database, fx)
    with database.session() as db:
        hk_rooms.get(db, fx.property_a.id, rooms["101"]).hk_status = HkStatus.dirty
    sup = login("supervisor@hvh.test")
    aid = sup.post(_hk(fx, "/assignments"), json={
        "roomIds": [rooms["101"]], "housekeeperUserId": fx.housekeeper_a.id}).get_json()[0]["id"]
    res = sup.delete(_hk(fx, f"/assignments/{aid}"))
    assert res.status_code == 200
    assert res.get_json()["assignment"] is None
