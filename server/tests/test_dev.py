from app import create_app
from app.config import Config
from tests.factories import inbound


def test_dev_routes_absent_in_production(template_db_path, tmp_path):
    import shutil

    p = tmp_path / "prod.db"
    shutil.copy(template_db_path, p)
    app = create_app(Config(DATABASE_URL=f"sqlite:///{p.as_posix()}", ENV="production", TESTING=True))
    assert app.test_client().get("/api/dev/sim/guests").status_code == 404
    app.extensions["db"].engine.dispose()


def test_sim_guests_and_thread(app, fx, client):
    guests = client.get("/api/dev/sim/guests").get_json()
    sarah = [g for g in guests if g["phone"] == fx.guest_inhouse_a.phone_e164][0]
    assert sarah["roomNumber"] == "412" and sarah["propertyId"] == fx.property_a.id and sarah["willFail"] is False
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    t = client.get(f"/api/dev/sim/thread?phone={fx.guest_inhouse_a.phone_e164}&propertyId={fx.property_a.id}").get_json()
    assert [m["body"] for m in t["messages"]] == ["hello"] and "notes" not in t


def test_sim_events_ring_buffer(app, fx, client):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    events = client.get("/api/dev/sim/events").get_json()
    assert any(e["type"] == "message.created" for e in events)
    assert all({"type", "propertyId", "at", "payload"} <= set(e) for e in events)


def test_dev_pms_endpoints(app, fx, client, database):
    from sqlalchemy import select

    from app.models import Stay
    from app.schemas.enums import StayStatus

    assert client.post(f"/api/dev/pms/check-out/{fx.stay_inhouse_a.id}").status_code == 204
    with database.session() as db:
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_out
    assert client.post("/api/dev/pms/check-in/nope").status_code == 404
