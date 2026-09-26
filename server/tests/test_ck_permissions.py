"""Checklists spec §4.3. Every one includes admin — test_isolation.py demands it."""
from app.auth.permissions import CAPABILITIES, STAFF, has_capability
from app.schemas.enums import Role


def test_checklist_capabilities_match_the_spec():
    assert CAPABILITIES["view_checklists"] == STAFF
    assert CAPABILITIES["perform_checklists"] == {Role.agent, Role.dept_staff, Role.supervisor,
                                                  Role.manager, Role.admin}
    assert CAPABILITIES["manage_checklists"] == {Role.supervisor, Role.manager, Role.admin}
    for cap in ("view_checklists", "perform_checklists", "manage_checklists"):
        assert has_capability(Role.admin, cap), cap
    assert not has_capability(Role.corporate, "perform_checklists")
    assert not has_capability(Role.dept_staff, "manage_checklists")
