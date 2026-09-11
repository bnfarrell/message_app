"""Drives the real WebSocket route with a dev server in a thread and simple_websocket's client."""
import json
import threading

import pytest
from werkzeug.serving import make_server


@pytest.fixture()
def live_server(app):
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _cookie(login):
    c = login("agent@hvh.test")
    return "sid=" + c.get_cookie("sid").value


def _connect(host, cookie):
    from simple_websocket import Client

    return Client.connect(f"ws://{host}/ws", headers={"Cookie": cookie})


def test_unauthenticated_socket_is_closed(live_server):
    from simple_websocket import Client, ConnectionClosed

    ws = Client.connect(f"ws://{live_server}/ws")
    with pytest.raises(ConnectionClosed):
        ws.receive(timeout=2)


def test_subscribe_and_receive_broadcast(app, fx, live_server, login, database):
    ws = _connect(live_server, _cookie(login))
    ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_a.id}))
    assert json.loads(ws.receive(timeout=2))["type"] == "subscribed"
    from app.domain import notifications

    with database.session() as db:
        notifications.create(db, fx.property_a.id, fx.agent_a.id, "t", "Hello over the wire")
    msg = json.loads(ws.receive(timeout=2))
    assert (msg["type"] == "notification.created"
           and msg["payload"]["title"] == "Hello over the wire")
    ws.close()


def test_subscribe_to_other_property_is_refused(app, fx, live_server, login):
    from simple_websocket import ConnectionClosed

    ws = _connect(live_server, _cookie(login))
    ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_b.id}))
    with pytest.raises(ConnectionClosed):
        ws.receive(timeout=2)


def test_presence_is_fanned_out_to_the_property(app, fx, live_server, login, database):
    from tests.factories import make_conversation

    with database.session() as db:
        conv_id = make_conversation(db, fx).id
    a = _connect(live_server, _cookie(login))
    b = _connect(live_server, "sid=" + login("agent2@hvh.test").get_cookie("sid").value)
    for ws in (a, b):
        ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_a.id}))
        assert json.loads(ws.receive(timeout=2))["type"] == "subscribed"
    a.send(json.dumps({"type": "presence", "conversationId": conv_id, "state": "composing"}))
    got = json.loads(b.receive(timeout=2))
    assert got["type"] == "presence.update" and got["payload"]["conversationId"] == conv_id
    assert (got["payload"]["users"][0]["firstName"] == "Ava"
           and got["payload"]["users"][0]["state"] == "composing")
    a.close()
    b.close()


def test_disconnect_clears_presence(app, fx, live_server, login, database):
    from tests.factories import make_conversation

    with database.session() as db:
        conv_id = make_conversation(db, fx).id
    a = _connect(live_server, _cookie(login))
    b = _connect(live_server, "sid=" + login("agent2@hvh.test").get_cookie("sid").value)
    for ws in (a, b):
        ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_a.id}))
        assert json.loads(ws.receive(timeout=2))["type"] == "subscribed"
    a.send(json.dumps({"type": "presence", "conversationId": conv_id, "state": "viewing"}))
    got = json.loads(b.receive(timeout=2))
    assert got["payload"]["conversationId"] == conv_id
    assert [u["id"] for u in got["payload"]["users"]] == [fx.agent_a.id]
    a.close()
    got2 = json.loads(b.receive(timeout=2))
    assert got2["type"] == "presence.update" and got2["payload"]["conversationId"] == conv_id
    assert got2["payload"]["users"] == []
    b.close()


def test_presence_for_foreign_conversation_is_refused(app, fx, live_server, login, database):
    """A conversationId belonging to a property the socket isn't subscribed to must never enter
    the shared presence store — otherwise the next legitimate user of that other property would
    see an impostor's name/avatar in their typing indicator (Task 19 review, Finding 2)."""
    from tests.factories import make_conversation

    with database.session() as db:
        foreign_conv_id = make_conversation(db, fx, guest=fx.guest_b).id
        own_conv_id = make_conversation(db, fx).id
    a = _connect(live_server, _cookie(login))
    b = _connect(live_server, "sid=" + login("agent2@hvh.test").get_cookie("sid").value)
    for ws in (a, b):
        ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_a.id}))
        assert json.loads(ws.receive(timeout=2))["type"] == "subscribed"
    a.send(json.dumps({"type": "presence", "conversationId": foreign_conv_id, "state": "viewing"}))
    # A second, legitimate presence frame on the same connection is processed after the first by
    # the single reader thread, so its broadcast proves the foreign one above was already handled.
    a.send(json.dumps({"type": "presence", "conversationId": own_conv_id, "state": "viewing"}))
    got = json.loads(b.receive(timeout=2))
    assert got["payload"]["conversationId"] == own_conv_id

    from app.realtime.presence import store

    assert store.snapshot(foreign_conv_id) == []
    a.close()
    b.close()
