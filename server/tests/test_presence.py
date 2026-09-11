from datetime import timedelta

from app import clock
from app.realtime.presence import PresenceStore

AVA = {"id": "u1", "firstName": "Ava", "avatarUrl": None}
MARCUS = {"id": "u2", "firstName": "Marcus", "avatarUrl": None}


def test_update_and_snapshot():
    s = PresenceStore()
    assert s.update("c1", AVA, "viewing") == {"c1"}
    assert s.update("c1", MARCUS, "composing") == {"c1"}
    snap = s.snapshot("c1")
    assert {(u["id"], u["state"]) for u in snap} == {("u1", "viewing"), ("u2", "composing")}


def test_moving_conversations_reports_both():
    s = PresenceStore()
    s.update("c1", AVA, "viewing")
    assert s.update("c2", AVA, "viewing") == {"c1", "c2"}
    assert s.snapshot("c1") == [] and [u["id"] for u in s.snapshot("c2")] == ["u1"]


def test_null_conversation_clears():
    s = PresenceStore()
    s.update("c1", AVA, "viewing")
    assert s.update(None, AVA, "viewing") == {"c1"}
    assert s.snapshot("c1") == []


def test_sweep_expires_stale_entries():
    s = PresenceStore()
    clock.freeze(clock.now())
    s.update("c1", AVA, "viewing")
    clock.advance(seconds=11)
    s.update("c1", MARCUS, "viewing")
    assert s.sweep(clock.now()) == {"c1"}
    assert [u["id"] for u in s.snapshot("c1")] == ["u2"]


def test_clear_user():
    s = PresenceStore()
    s.update("c1", AVA, "viewing")
    assert s.clear_user("u1") == {"c1"}
