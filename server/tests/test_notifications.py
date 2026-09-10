from app import clock
from app.domain import notifications
from app.schemas.enums import DepartmentType


def test_create_persists_and_broadcasts_to_user(app, fx, database, events):
    with database.session() as db:
        n = notifications.create(db, fx.property_a.id, fx.agent_a.id, "test", "Hello", body="b",
                                 entity_type="conversation", entity_id="c1")
    assert n.id
    ev = [e for e in events if e.type == "notification.created"]
    assert len(ev) == 1
    assert ev[0].user_id == fx.agent_a.id
    assert ev[0].property_id == fx.property_a.id
    assert ev[0].payload["title"] == "Hello"


def test_events_are_delivered_only_after_commit(app, fx, database, events):
    import pytest

    with pytest.raises(RuntimeError):
        with database.session() as db:
            notifications.create(db, fx.property_a.id, fx.agent_a.id, "test", "Never")
            raise RuntimeError("boom")
    assert events == []


def test_notify_user_or_department_prefers_user(app, fx, database):
    with database.session() as db:
        rows = notifications.notify_user_or_department(
            db, fx.property_a.id, user_id=fx.agent_a2.id, department_id=fx.dept_engineering.id,
            type="t", title="x")
    assert [r.user_id for r in rows] == [fx.agent_a2.id]


def test_notify_department_fans_out_to_members(app, fx, database):
    with database.session() as db:
        rows = notifications.notify_user_or_department(
            db, fx.property_a.id, user_id=None, department_id=fx.dept_engineering.id, type="t", title="x")
    assert sorted(r.user_id for r in rows) == sorted([fx.engineer_a.id, fx.supervisor_a.id])


def test_notify_falls_back_to_front_desk(app, fx, database):
    with database.session() as db:
        rows = notifications.notify_user_or_department(
            db, fx.property_a.id, user_id=None, department_id=None, type="t", title="x")
    assert sorted(r.user_id for r in rows) == sorted([fx.agent_a.id, fx.agent_a2.id])


def test_list_mark_read_and_unread_count_via_api(app, fx, database, login):
    # The clock is frozen, so "newest first" only means something if time actually moves between
    # the two notifications — otherwise their created_at values tie and the order is arbitrary.
    with database.session() as db:
        notifications.create(db, fx.property_a.id, fx.agent_a.id, "t", "One")
    clock.advance(seconds=1)
    with database.session() as db:
        notifications.create(db, fx.property_a.id, fx.agent_a.id, "t", "Two")
        notifications.create(db, fx.property_a.id, fx.agent_a2.id, "t", "Not mine")
    c = login("agent@hvh.test")
    base = f"/api/p/{fx.property_a.id}/notifications"
    rows = c.get(base).get_json()
    assert [r["title"] for r in rows] == ["Two", "One"]
    assert c.get(base + "/unread-count").get_json() == {"count": 2}
    assert c.post(f"{base}/{rows[0]['id']}/read").status_code == 204
    assert c.get(base + "?unread=1").get_json()[0]["title"] == "One"
    assert c.post(base + "/read-all").status_code == 204
    assert c.get(base + "/unread-count").get_json() == {"count": 0}


def test_cannot_mark_someone_elses_notification(app, fx, database, login):
    with database.session() as db:
        n = notifications.create(db, fx.property_a.id, fx.agent_a2.id, "t", "Not mine")
    c = login("agent@hvh.test")
    assert c.post(f"/api/p/{fx.property_a.id}/notifications/{n.id}/read").status_code == 404
