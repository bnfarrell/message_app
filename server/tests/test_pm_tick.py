"""The recurring job (spec §4.1) and the scheduled-run lifecycle through the Board."""
from datetime import UTC, datetime

from sqlalchemy import func, select

from app import clock
from app.models import PmCycle, PmRun, PmTemplate, WorkOrder
from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all
from app.queue.handlers.pm import tick_once
from app.schemas.enums import PmCycleStatus, PmRunStatus, WorkOrderStatus
from tests.test_pm_runs import setup_sweep


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def test_registered_as_a_recurring_job():
    load_all()
    assert "pm.tick" in HANDLERS and jobs.RECURRING["pm.tick"] == 300


def test_tick_rolls_an_expired_cycle_and_opens_the_next(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("204", "205"))
    with database.session() as db:
        assert tick_once(db) == {"opened": 0, "missed": 0, "fired": 0}
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        assert tick_once(db) == {"opened": 1, "missed": 2, "fired": 0}
        cycles = db.scalars(select(PmCycle).where(PmCycle.template_id == template_id)
                            .order_by(PmCycle.starts_on)).all()
        assert [(c.ordinal, c.status) for c in cycles] == [
            (3, PmCycleStatus.closed), (4, PmCycleStatus.open)]
        assert db.scalar(select(func.count()).select_from(PmRun).where(
            PmRun.status == PmRunStatus.missed)) == 2
        assert tick_once(db) == {"opened": 0, "missed": 0, "fired": 0}, "idempotent"


def _scheduled(admin, fx, unit_ids, rrule="FREQ=MONTHLY;INTERVAL=3", dtstart="2026-07-01"):
    res = admin.post(_pm(fx, "/templates"), json={
        "name": "Boiler inspection", "mode": "scheduled", "rrule": rrule,
        "rruleDtstart": dtstart, "departmentId": fx.dept_engineering.id,
        "unitIds": unit_ids,
        "items": [{"label": "Pressure", "itemType": "number", "unit": "psi",
                   "minValue": 10, "maxValue": 30}]})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"]


def _units(admin, fx, *codes):
    return [admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                       json={"kind": "equipment", "code": c, "name": c}).get_json()["id"]
            for c in codes]


def test_rrule_fires_once_per_occurrence_per_unit_after_creation_never_before(
        app, fx, login, database):
    admin = login("admin@hvh.test")
    boilers = _units(admin, fx, "BOILER-1", "BOILER-2")
    template_id = _scheduled(admin, fx, boilers)  # created 2026-09-10; Jul 1 is in the past
    with database.session() as db:
        assert db.get(PmTemplate, template_id).last_fired_at == clock.now()
        assert tick_once(db)["fired"] == 0, "no backfill of the July occurrence"
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))  # Oct 1 occurrence has passed
    with database.session() as db:
        assert tick_once(db)["fired"] == 2
        runs = db.scalars(select(PmRun).where(PmRun.template_id == template_id)).all()
        assert {r.status for r in runs} == {PmRunStatus.pending}
        assert {r.unit_id for r in runs} == set(boilers)
        assert all(r.due_at == datetime(2026, 10, 1, 4, 0, tzinfo=UTC) for r in runs)  # EDT
        wos = db.scalars(select(WorkOrder).where(WorkOrder.type == "pm")).all()
        assert len(wos) == 2 and {w.id for w in wos} == {r.work_order_id for r in runs}
        assert wos[0].title.startswith("Boiler inspection — BOILER-")
        assert wos[0].department_id == fx.dept_engineering.id
        assert wos[0].location_type.value == "equipment"
        assert tick_once(db)["fired"] == 0, "the window advanced"
    clock.freeze(datetime(2027, 1, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        assert tick_once(db)["fired"] == 2


def test_an_inactive_target_unit_is_skipped(app, fx, login, database):
    admin = login("admin@hvh.test")
    b1, b2 = _units(admin, fx, "BOILER-1", "BOILER-2")
    _scheduled(admin, fx, [b1, b2])
    admin.patch(f"/api/p/{fx.property_a.id}/maintainable-units/{b2}", json={"active": False})
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        assert tick_once(db)["fired"] == 1


def test_scheduled_run_drives_its_work_order_start_complete_verify(app, fx, login, database):
    admin = login("admin@hvh.test")
    (boiler,) = _units(admin, fx, "BOILER-1")
    _scheduled(admin, fx, [boiler])
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        tick_once(db)
        run_id = db.scalar(select(PmRun.id))
        wo_id = db.scalar(select(PmRun.work_order_id))
    eng = login("engineer@hvh.test")
    detail = eng.get(f"/api/p/{fx.property_a.id}/work-orders/{wo_id}").get_json()
    assert detail["pmRunId"] == run_id and detail["status"] == "open"

    run = eng.get(_pm(fx, f"/runs/{run_id}")).get_json()
    assert run["status"] == "pending" and run["answers"] == []
    res = eng.post(_pm(fx, f"/runs/{run_id}/start"))
    assert res.status_code == 200 and res.get_json()["status"] == "in_progress"
    assert len(res.get_json()["answers"]) == 1
    assert eng.post(_pm(fx, f"/runs/{run_id}/start")).status_code == 409
    with database.session() as db:
        assert db.get(WorkOrder, wo_id).status == WorkOrderStatus.in_progress

    answer = res.get_json()["answers"][0]
    eng.patch(_pm(fx, f"/runs/{run_id}/answers/{answer['id']}"), json={"numberValue": 20})
    assert eng.post(_pm(fx, f"/runs/{run_id}/complete")).status_code == 200
    with database.session() as db:
        assert db.get(WorkOrder, wo_id).status == WorkOrderStatus.complete

    sup = login("supervisor@hvh.test")
    assert sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "pass"}).status_code == 200
    with database.session() as db:
        assert db.get(WorkOrder, wo_id).status == WorkOrderStatus.verified
