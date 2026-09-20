from app.auth.permissions import CAPABILITIES, has_capability
from app.schemas.enums import Role


def test_pm_capabilities_match_the_spec():
    """Spec §6. Every one includes admin — test_isolation.py demands it."""
    assert CAPABILITIES["view_pm"] == {Role.agent, Role.dept_staff, Role.supervisor,
                                       Role.manager, Role.admin, Role.corporate}
    assert CAPABILITIES["perform_pm"] == {Role.dept_staff, Role.supervisor, Role.manager,
                                          Role.admin}
    assert CAPABILITIES["inspect_pm"] == {Role.supervisor, Role.manager, Role.admin}
    for cap in ("view_pm", "perform_pm", "inspect_pm"):
        assert has_capability(Role.admin, cap), cap
    assert not has_capability(Role.agent, "perform_pm")
    assert not has_capability(Role.dept_staff, "inspect_pm")
