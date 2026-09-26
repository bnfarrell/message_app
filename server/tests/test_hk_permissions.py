"""Spec §4.2. Every one includes admin — test_isolation.py demands it."""
from app.auth.permissions import CAPABILITIES, STAFF, has_capability
from app.schemas.enums import Role

HK = ("view_housekeeping", "mark_room_dirty", "perform_housekeeping", "manage_housekeeping",
      "inspect_housekeeping")


def test_housekeeping_capabilities_match_the_spec():
    assert CAPABILITIES["view_housekeeping"] == STAFF
    assert CAPABILITIES["mark_room_dirty"] == {Role.agent, Role.dept_staff, Role.supervisor,
                                               Role.manager, Role.admin}
    assert CAPABILITIES["perform_housekeeping"] == {Role.dept_staff, Role.supervisor,
                                                    Role.manager, Role.admin}
    assert CAPABILITIES["manage_housekeeping"] == {Role.supervisor, Role.manager, Role.admin}
    assert CAPABILITIES["inspect_housekeeping"] == {Role.supervisor, Role.manager, Role.admin}


def test_admin_holds_every_housekeeping_capability():
    for cap in HK:
        assert has_capability(Role.admin, cap), cap


def test_front_desk_can_mark_dirty_but_not_run_the_floor():
    assert has_capability(Role.agent, "mark_room_dirty")
    for cap in ("perform_housekeeping", "manage_housekeeping", "inspect_housekeeping"):
        assert not has_capability(Role.agent, cap), cap
    assert not has_capability(Role.corporate, "mark_room_dirty")
