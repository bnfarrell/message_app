"""design.md §11.1 #9: a member of Property A gets 403 on every Property B resource.

Enumerates every rule under /api/p/<property_id> so new routes are covered automatically.
"""
import re

SKIP_METHODS = {"HEAD", "OPTIONS"}
DUMMY_ID = "00000000-0000-0000-0000-000000000000"


def property_rules(app):
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/p/<property_id>"):
            for method in sorted(rule.methods - SKIP_METHODS):
                yield rule, method


def build_path(rule, property_id: str) -> str:
    path = rule.rule.replace("<property_id>", property_id)
    return re.sub(r"<[^>]+>", DUMMY_ID, path)  # 403 must fire before any lookup


def test_route_enumeration_finds_routes(app):
    assert len(list(property_rules(app))) >= 2


def test_member_of_a_gets_403_on_every_b_route(app, fx, login):
    c = login("admin@hvh.test")  # admin at A, no membership at B
    failures = []
    for rule, method in property_rules(app):
        res = c.open(build_path(rule, fx.property_b.id), method=method, json={})
        if res.status_code != 403:
            failures.append((method, rule.rule, res.status_code))
    assert not failures, f"routes reachable across properties: {failures}"


def test_admin_of_a_is_not_403_on_own_property(app, fx, login):
    """Guards the previous test against vacuity: the same routes must not 403 for a member."""
    c = login("admin@hvh.test")
    failures = []
    for rule, method in property_rules(app):
        res = c.open(build_path(rule, fx.property_a.id), method=method, json={})
        if res.status_code == 403:
            failures.append((method, rule.rule))
    assert not failures, f"admin blocked on own property: {failures}"


def test_anonymous_gets_401_on_every_property_route(app, fx, client):
    for rule, method in property_rules(app):
        res = client.open(build_path(rule, fx.property_a.id), method=method, json={})
        assert res.status_code == 401, (method, rule.rule, res.status_code)
