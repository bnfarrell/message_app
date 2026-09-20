"""Sweep page payload and cycle history (spec §5.3, §5.2)."""
from datetime import date

from app.domain import pm_cycles
from app.models import PmTemplate
from tests.test_pm_inspection import complete_run
from tests.test_pm_runs import setup_sweep, start


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def test_sweep_without_a_template_reports_the_kind_as_unconfigured(app, fx, login):
    admin = login("admin@hvh.test")
    admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
               json={"kind": "equipment", "code": "PUMP", "name": "Pump"})
    body = login("agent@hvh.test").get(_pm(fx, "/sweep?kind=equipment")).get_json()
    assert body["template"] is None and body["cycle"] is None
    assert body["counts"] == {"remaining": 1, "completed": 0, "total": 1}
    assert body["units"] == []
    assert login("agent@hvh.test").get(_pm(fx, "/sweep")).status_code == 400  # kind required


def test_sweep_counts_rows_filters_and_sorting(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("101", "204", "205"))
    eng = login("engineer@hvh.test")
    sup = login("supervisor@hvh.test")
    passed_run = complete_run(eng, fx, template_id, units["204"])
    sup.post(_pm(fx, f"/runs/{passed_run}/inspect"), json={"result": "pass"})
    in_progress = start(eng, fx, template_id, units["205"])

    body = eng.get(_pm(fx, "/sweep?kind=guest_room")).get_json()
    assert body["template"]["name"] == "Guest Room Quarterly"
    assert body["cycle"]["ordinal"] == 3 and body["cycle"]["daysLeft"] == 20  # Sep 10 → Sep 30
    assert body["counts"] == {"remaining": 2, "completed": 1, "total": 3}
    by_code = {u["code"]: u for u in body["units"]}
    assert list(by_code) == ["101", "204", "205"]
    assert by_code["204"]["passedThisCycle"] is True and by_code["204"]["currentRun"] is None
    assert by_code["204"]["lastPassedByName"] == "Eli Engineer"
    assert by_code["205"]["currentRun"] == {"id": in_progress["id"], "status": "in_progress",
                                             "startedByUserId": fx.engineer_a.id,
                                             "startedByName": "Eli Engineer"}
    assert by_code["101"]["currentRun"] is None and by_code["101"]["lastPassedAt"] is None

    remaining = eng.get(_pm(fx, "/sweep?kind=guest_room&status=remaining")).get_json()
    assert [u["code"] for u in remaining["units"]] == ["101", "205"]
    completed = eng.get(_pm(fx, "/sweep?kind=guest_room&status=completed")).get_json()
    assert [u["code"] for u in completed["units"]] == ["204"]
    q20 = eng.get(_pm(fx, "/sweep?kind=guest_room&q=20")).get_json()
    assert [u["code"] for u in q20["units"]] == ["204", "205"]
    by_days = eng.get(_pm(fx, "/sweep?kind=guest_room&sort=days_since_last_pm")).get_json()
    assert [u["code"] for u in by_days["units"]] == ["101", "205", "204"]  # never first
    by_floor = eng.get(_pm(fx, "/sweep?kind=guest_room&sort=floor")).get_json()
    assert [u["code"] for u in by_floor["units"]] == ["101", "204", "205"]


def test_cycle_history_after_a_close(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("204", "205", "206"))
    eng = login("engineer@hvh.test")
    sup = login("supervisor@hvh.test")
    run = complete_run(eng, fx, template_id, units["204"])
    sup.post(_pm(fx, f"/runs/{run}/inspect"), json={"result": "pass"})
    with database.session() as db:
        t = db.get(PmTemplate, template_id)
        assert pm_cycles.close_expired(db, t, date(2026, 10, 1)) == 2
        pm_cycles.ensure_open_cycle(db, t, date(2026, 10, 1))
    rows = eng.get(_pm(fx, f"/cycles?templateId={template_id}")).get_json()
    assert [(r["ordinal"], r["status"]) for r in rows] == [(4, "open"), (3, "closed")]
    q3 = rows[1]
    assert (q3["passed"], q3["missed"], q3["total"]) == (1, 2, 3)
    assert q3["daysLeft"] == 0


def test_compliance_per_template_cycles_runs_and_inspection_rate(app, fx, login, database):
    from datetime import UTC, datetime

    from app import clock
    from app.queue.handlers.pm import tick_once

    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("204", "205", "206", "207"))
    eng = login("engineer@hvh.test")
    sup = login("supervisor@hvh.test")
    passed = complete_run(eng, fx, template_id, units["204"])
    sup.post(_pm(fx, f"/runs/{passed}/inspect"), json={"result": "pass"})
    failed = complete_run(eng, fx, template_id, units["205"])
    sup.post(_pm(fx, f"/runs/{failed}/inspect"), json={"result": "fail", "note": "Redo"})
    boiler = admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                        json={"kind": "equipment", "code": "B1", "name": "Boiler 1"}).get_json()
    _sched = admin.post(_pm(fx, "/templates"), json={
        "name": "Boiler inspection", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3",
        "rruleDtstart": "2026-07-01", "unitIds": [boiler["id"]],
        "items": [{"label": "Pressure", "itemType": "number"}]}).get_json()["id"]

    clock.freeze(datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    with database.session() as db:
        tick_once(db)  # closes Q3 (3 missed: 205, 206, 207), opens Q4, fires Oct 1 → 1 overdue run

    body = login("manager@hvh.test").get(
        _pm(fx, "/compliance?from=2026-07-01&to=2026-12-31")).get_json()
    by_name = {t["name"]: t for t in body["templates"]}
    rooms = by_name["Guest Room Quarterly"]
    assert rooms["mode"] == "sweep" and rooms["runs"] is None
    q3 = next(c for c in rooms["cycles"] if c["ordinal"] == 3)
    assert (q3["passed"], q3["missed"], q3["total"], q3["onTimePct"]) == (1, 3, 4, 25.0)
    assert rooms["inspectionPassRate"] == 50.0
    boilers = by_name["Boiler inspection"]
    assert boilers["cycles"] == []
    assert boilers["runs"] == {"due": 1, "passed": 0, "failed": 0, "overdue": 1}
    assert boilers["inspectionPassRate"] is None

    assert login("engineer@hvh.test").get(
        _pm(fx, "/compliance?from=2026-07-01&to=2026-12-31")).status_code == 403
    assert login("manager@hvh.test").get(_pm(fx, "/compliance?from=nope&to=2026-12-31")) \
        .status_code == 400
