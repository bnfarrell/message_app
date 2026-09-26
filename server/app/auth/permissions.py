from app.schemas.enums import Role

STAFF = {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin, Role.corporate}

# Mirrors docs/design.md §3.2 for the Phase 1 capabilities.
CAPABILITIES: dict[str, set[Role]] = {
    "view_all_conversations": {Role.agent, Role.supervisor, Role.manager, Role.admin,
                              Role.corporate},
    "reply": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "assign": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "add_note": STAFF,
    "archive": {Role.agent, Role.supervisor, Role.manager, Role.admin},
    "create_work_order": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "close_work_order": {Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "view_property_analytics": {Role.supervisor, Role.manager, Role.admin, Role.corporate},
    "view_own_stats": {Role.agent, Role.dept_staff},
    "manage_admin": {Role.admin, Role.corporate},
    "export": {Role.manager, Role.admin, Role.corporate},
    "view_log": STAFF,
    "post_log": STAFF,
    "pin_log_entry": {Role.supervisor, Role.manager, Role.admin},
    # Preventative maintenance (PM spec §6). All three include admin: the isolation suite
    # asserts a property's admin is never 403 on a property route.
    "view_pm": STAFF,
    "perform_pm": {Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "inspect_pm": {Role.supervisor, Role.manager, Role.admin},
    # Housekeeping (spec §4.2). All include admin, as above. Front desk (agent) can see the
    # board and mark a room dirty or rush it, and nothing more.
    "view_housekeeping": STAFF,
    "mark_room_dirty": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "perform_housekeeping": {Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "manage_housekeeping": {Role.supervisor, Role.manager, Role.admin},
    "inspect_housekeeping": {Role.supervisor, Role.manager, Role.admin},
}


def has_capability(role: Role, capability: str) -> bool:
    return role in CAPABILITIES.get(capability, set())
