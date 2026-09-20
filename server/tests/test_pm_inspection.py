"""Inspection (spec §4.4, §5.2)."""
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.domain import pm_inspection
from app.errors import Forbidden
from app.models import Notification, PmRun, PropertyMembership
from app.schemas.enums import PmRunStatus, Role
from app.schemas.pm import InspectRequest
from tests.test_pm_runs import PNG, answer_by_label, setup_sweep, start, upload


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def complete_run(client, fx, template_id, unit_id, temperature=110):
    run = start(client, fx, template_id, unit_id)
    path = _pm(fx, f"/runs/{run['id']}")
    hvac, _ = answer_by_label(run, "HVAC filter replaced")
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    _, fan = answer_by_label(run, "Bathroom fan photo")
    client.patch(f"{path}/answers/{hvac['id']}", json={"boolValue": True})
    client.patch(f"{path}/answers/{temp['id']}", json={"numberValue": temperature})
    upload(client, fx, run["id"], PNG, item_id=fan["id"])
    res = client.post(f"{path}/complete")
    assert res.status_code == 200, res.get_json()
    return run["id"]


def test_queue_lists_completed_runs_and_pass_credits_the_unit(app, fx, login, events):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run_id = complete_run(eng, fx, template_id, units["204"])
    sup = login("supervisor@hvh.test")

    rows = sup.get(_pm(fx, "/inspections?kind=guest_room")).get_json()
    assert [r["runId"] for r in rows] == [run_id]
    assert rows[0]["completedByName"] == "Eli Engineer" and rows[0]["daysSinceLastPm"] is None
    assert sup.get(_pm(fx, "/inspections?kind=equipment")).get_json() == []
    assert sup.get(_pm(fx, "/inspections?status=inspected")).get_json() == []

    res = sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "pass"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["status"] == "passed"
    assert res.get_json()["inspectedByName"] == "Sam Super"
    assert sup.get(_pm(fx, "/inspections")).get_json() == []
    inspected = sup.get(_pm(fx, "/inspections?status=inspected")).get_json()
    assert inspected[0]["status"] == "passed" and inspected[0]["inspectedByName"] == "Sam Super"

    # A passed unit cannot be started again this cycle.
    res = eng.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": units["204"]})
    assert res.status_code == 409
    assert "details" not in res.get_json()["error"], "no Continue offered for a passed unit"
    assert any(e.type == "pm.run.changed" and e.payload["status"] == "passed" for e in events)


def test_fail_needs_a_note_notifies_the_engineer_and_returns_the_unit_to_remaining(
        app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run_id = complete_run(eng, fx, template_id, units["204"])
    sup = login("supervisor@hvh.test")

    assert sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "fail"}).status_code == 400
    res = sup.post(_pm(fx, f"/runs/{run_id}/inspect"),
                   json={"result": "fail", "note": "Fan photo shows the grille still dusty."})
    assert res.status_code == 200 and res.get_json()["status"] == "failed"
    assert res.get_json()["inspectionNote"].startswith("Fan photo")
    with database.session() as db:
        notes = db.scalars(select(Notification).where(
            Notification.type == "pm.inspection_failed")).all()
        assert [n.user_id for n in notes] == [fx.engineer_a.id]
        assert notes[0].entity_id == run_id

    # Back in Remaining: a fresh run can start, and the failed one is a permanent record.
    new = start(eng, fx, template_id, units["204"])
    assert new["id"] != run_id
    with database.session() as db:
        assert db.get(PmRun, run_id).status == PmRunStatus.failed


def test_a_run_is_inspected_once_and_not_by_its_own_engineer(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    sup = login("supervisor@hvh.test")
    run_id = complete_run(sup, fx, template_id, units["204"])  # the supervisor did the PM
    assert sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "pass"}).status_code == 403
    manager = login("manager@hvh.test")
    assert manager.post(_pm(fx, f"/runs/{run_id}/inspect"),
                        json={"result": "pass"}).status_code == 200
    assert manager.post(_pm(fx, f"/runs/{run_id}/inspect"),
                        json={"result": "pass"}).status_code == 409
    assert login("engineer@hvh.test").post(_pm(fx, f"/runs/{run_id}/inspect"),
                                           json={"result": "pass"}).status_code == 403


def test_the_sole_inspector_may_inspect_their_own_run(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    sup = login("supervisor@hvh.test")
    run_id = complete_run(sup, fx, template_id, units["204"])
    with database.session() as db:
        # Demote every other inspect_pm holder at property A.
        for m in db.scalars(select(PropertyMembership).where(
                PropertyMembership.property_id == fx.property_a.id,
                PropertyMembership.role.in_([Role.manager, Role.admin]))).all():
            m.role = Role.agent
        db.flush()
        try:
            pm_inspection.inspect(db, fx.property_a.id, fx.supervisor_a.id, run_id,
                                  InspectRequest(result="pass"))
        except Forbidden:
            raise AssertionError("the only inspector must be allowed to inspect") from None
        assert db.get(PmRun, run_id).status == PmRunStatus.passed


def test_days_since_last_pm_counts_from_the_units_previous_pass(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    with database.session() as db:
        db.add(PmRun(property_id=fx.property_a.id, template_id=template_id,
                     unit_id=units["204"], status=PmRunStatus.passed,
                     started_at=clock.now() - timedelta(days=31),
                     completed_at=clock.now() - timedelta(days=30),
                     inspected_at=clock.now() - timedelta(days=29)))
    eng = login("engineer@hvh.test")
    complete_run(eng, fx, template_id, units["204"])
    complete_run(eng, fx, template_id, units["205"])
    rows = login("supervisor@hvh.test").get(
        _pm(fx, "/inspections?sort=days_since_last_pm")).get_json()
    # Never-inspected sorts first, then the longest-ago.
    assert [(r["unitCode"], r["daysSinceLastPm"]) for r in rows] == [("205", None), ("204", 30)]
