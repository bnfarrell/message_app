from app import create_app
from app.config import Config
from tests.factories import inbound


def test_dev_routes_absent_in_production(template_db_path, tmp_path):
    import shutil

    p = tmp_path / "prod.db"
    shutil.copy(template_db_path, p)
    app = create_app(Config(DATABASE_URL=f"sqlite:///{p.as_posix()}", ENV="production",
                            TESTING=True))
    assert app.test_client().get("/api/dev/sim/guests").status_code == 404
    app.extensions["db"].engine.dispose()


def test_sim_guests_and_thread(app, fx, client):
    guests = client.get("/api/dev/sim/guests").get_json()
    sarah = [g for g in guests if g["phone"] == fx.guest_inhouse_a.phone_e164][0]
    assert (sarah["roomNumber"] == "412" and sarah["propertyId"] == fx.property_a.id
           and sarah["willFail"] is False)
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    t = client.get(f"/api/dev/sim/thread?phone={fx.guest_inhouse_a.phone_e164}"
                   f"&propertyId={fx.property_a.id}").get_json()
    assert [m["body"] for m in t["messages"]] == ["hello"] and "notes" not in t


def test_sim_events_ring_buffer(app, fx, client):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    events = client.get("/api/dev/sim/events").get_json()
    assert any(e["type"] == "message.created" for e in events)
    assert all({"type", "propertyId", "at", "payload"} <= set(e) for e in events)


def test_dev_pms_endpoints(app, fx, client, database):

    from app.models import Stay
    from app.schemas.enums import StayStatus

    assert client.post(f"/api/dev/pms/check-out/{fx.stay_inhouse_a.id}").status_code == 204
    with database.session() as db:
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_out
    assert client.post("/api/dev/pms/check-in/nope").status_code == 404


def test_dev_pms_check_in_succeeds(app, fx, client, database):
    from app.models import Stay
    from app.schemas.enums import StayStatus

    assert client.post(f"/api/dev/pms/check-out/{fx.stay_inhouse_a.id}").status_code == 204
    assert client.post(f"/api/dev/pms/check-in/{fx.stay_inhouse_a.id}").status_code == 204
    with database.session() as db:
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_in


def test_sim_thread_requires_query_params_and_a_real_property(app, fx, client):
    phone = fx.guest_inhouse_a.phone_e164
    assert client.get(f"/api/dev/sim/thread?phone={phone}").status_code == 400
    assert client.get("/api/dev/sim/thread?propertyId=" + fx.property_a.id).status_code == 400
    assert client.get(f"/api/dev/sim/thread?phone={phone}&propertyId=nope").status_code == 404


def test_sim_events_since_filters_and_rejects_garbage(app, fx, client):
    import uuid
    from urllib.parse import quote

    from app import clock

    # The ring buffer is process-global (inherited from the brief's design) and this test may run
    # in a suite alongside others that also emit events at overlapping frozen-clock timestamps, so
    # identify this test's own events by a unique marker rather than assuming the buffer is empty
    # or that it contains only this test's events.
    marker = uuid.uuid4().hex
    first_body, second_body = f"first-{marker}", f"second-{marker}"

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, first_body)
    cutoff = clock.now().isoformat()
    clock.advance(seconds=1)
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, second_body)

    events = client.get(f"/api/dev/sim/events?since={quote(cutoff)}").get_json()
    bodies = {e["payload"].get("body") for e in events if e["type"] == "message.created"}
    assert second_body in bodies
    assert first_body not in bodies

    assert client.get("/api/dev/sim/events?since=not-a-timestamp").status_code == 400
