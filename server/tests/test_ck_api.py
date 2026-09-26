"""The checklists HTTP surface (checklists spec §4.2, §4.3)."""
import io

from app.domain import ck_instances
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _ck(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/checklists{rest}"


def _instance(database, fx):
    with database.session() as db:
        inst, _ = ck_instances.ensure_instance(db, make_template(db, fx),
                                               local_today(db, fx.property_a.id))
        return inst.id


def test_the_whole_loop_over_http(database, fx, login):
    iid = _instance(database, fx)
    eli = login("engineer@hvh.test")
    body = eli.post(_ck(fx, f"/instances/{iid}/start")).get_json()
    assert body["status"] == "in_progress"
    by_label = {i["label"]: i for i in body["items"]}
    answer_for = {a["itemId"]: a for a in body["answers"]}
    for label, patch in (("Skimmer baskets emptied", {"boolValue": True}),
                         ("Pool pH", {"numberValue": 8.1})):
        res = eli.patch(_ck(fx, f"/instances/{iid}/answers/"
                                f"{answer_for[by_label[label]['id']]['id']}"), json=patch)
        assert res.status_code == 200, res.get_json()
    up = eli.post(_ck(fx, f"/instances/{iid}/photos"),
                  data={"photo": (io.BytesIO(PNG), "p.png", "image/png"),
                        "itemId": by_label["Plant room photo"]["id"]},
                  content_type="multipart/form-data")
    assert up.status_code == 201, up.get_json()
    assert eli.get(up.get_json()["photos"][0]["url"]).data == PNG
    assert eli.patch(_ck(fx, f"/instances/{iid}"),
                     json={"comment": "Pool pH high"}).get_json()["comment"] == "Pool pH high"
    done = eli.post(_ck(fx, f"/instances/{iid}/complete")).get_json()
    assert (done["status"], done["outOfRangeCount"]) == ("complete", 1)


def test_capabilities(database, fx, login):
    iid = _instance(database, fx)
    corp = login("corporate@hvh.test")
    assert corp.get(_ck(fx, "/instances")).status_code == 200
    assert corp.post(_ck(fx, f"/instances/{iid}/start")).status_code == 403
    assert login("engineer@hvh.test").post(_ck(fx, f"/instances/{iid}/assign"),
                                           json={"userId": None}).status_code == 403
    assert login("agent@hvh.test").get(_ck(fx, "/missed")).status_code == 403
    assert login("manager@hvh.test").get(_ck(fx, "/missed")).status_code == 200


def test_other_department_gets_403_from_the_domain(database, fx, login):
    iid = _instance(database, fx)
    assert login("housekeeper@hvh.test").post(
        _ck(fx, f"/instances/{iid}/start")).status_code == 403


def test_create_template_and_start_on_demand(database, fx, login):
    admin = login("admin@hvh.test")
    res = admin.post(_ck(fx, "/templates"), json={
        "name": "Power Outage", "departmentId": fx.dept_engineering.id, "schedule": "on_demand",
        "items": [{"label": "Generator started", "itemType": "checkbox"}]})
    assert res.status_code == 201, res.get_json()
    started = login("engineer@hvh.test").post(_ck(fx, f"/templates/{res.get_json()['id']}/start"))
    assert started.status_code == 201 and started.get_json()["onDemand"] is True


def test_instances_of_another_property_are_404(database, fx, login):
    with database.session() as db:
        from app.models import ChecklistTemplate
        t = ChecklistTemplate(property_id=fx.property_b.id, name="B", schedule="on_demand",
                              department_id=fx.dept_front_desk.id)
        db.add(t)
        db.flush()
        tid = t.id
    assert login("admin@hvh.test").post(_ck(fx, f"/templates/{tid}/start")).status_code == 404
