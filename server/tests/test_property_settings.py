from sqlalchemy import select

from app.models import Property


def _settings_url(property_id: str) -> str:
    return f"/api/p/{property_id}/settings"


def test_get_settings_returns_the_whole_shape(app, fx, login):
    res = login("agent@hvh.test").get(_settings_url(fx.property_a.id))
    assert res.status_code == 200
    body = res.get_json()
    assert set(body) == {"id", "name", "code", "timezone", "address", "phone", "smsNumber",
                         "brand", "currency", "logoUrl", "primaryColor"}
    assert body["id"] == fx.property_a.id
    assert body["code"] == fx.property_a.code
    assert "settings" not in body  # the untyped JSON bag is never exposed


def test_patch_settings_updates_each_field(app, fx, database, login):
    url = _settings_url(fx.property_a.id)
    admin = login("admin@hvh.test")
    patch = {"name": "Harbourview Hotel & Spa", "timezone": "Europe/Lisbon",
             "address": "1 Harbour Way", "phone": "+15550111", "smsNumber": "+15550122",
             "brand": "Harbourview Collection", "currency": "eur",
             "logoUrl": "https://example.test/logo.png", "primaryColor": "#0F62FE"}
    res = admin.patch(url, json=patch)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    expected = patch | {"currency": "EUR"}  # currency is upper-cased, everything else as sent
    assert {k: body[k] for k in expected} == expected
    assert body["code"] == fx.property_a.code  # unchanged and not patchable
    assert admin.get(url).get_json() == body  # persisted, not just echoed
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        assert p.name == "Harbourview Hotel & Spa" and p.timezone == "Europe/Lisbon"
        assert p.settings  # the JSON bag is untouched by a settings patch


def test_patch_settings_normalises_phone_numbers(app, fx, login):
    """Inbound routing matches Property.sms_number against guests.normalize_phone(To), so a
    prettified number saved here would silently stop inbound SMS for the property."""
    admin = login("admin@hvh.test")
    body = admin.patch(_settings_url(fx.property_a.id),
                       json={"smsNumber": "(555) 012-3456", "phone": "555 012 3457"}).get_json()
    assert body["smsNumber"] == "+15550123456" and body["phone"] == "+15550123457"
    assert admin.patch(_settings_url(fx.property_a.id),
                       json={"smsNumber": "not a phone"}).status_code == 400


def test_patch_settings_rejects_a_bad_timezone(app, fx, database, login):
    admin = login("admin@hvh.test")
    for bad in ("America/Nowhere", "EST5EDT7", "../../etc/passwd", ""):
        res = admin.patch(_settings_url(fx.property_a.id), json={"timezone": bad})
        assert res.status_code == 400, (bad, res.status_code)
    assert admin.patch(_settings_url(fx.property_a.id),
                       json={"timezone": "Asia/Tokyo"}).status_code == 200
    with database.session() as db:
        assert db.scalar(select(Property.timezone)
                         .where(Property.id == fx.property_a.id)) == "Asia/Tokyo"


def test_patch_settings_rejects_code_and_out_of_range_values(app, fx, database, login):
    """`code` is unique across the install and identifies the property: CamelModel forbids extra
    fields, so sending it is a 400 rather than a silent no-op."""
    url = _settings_url(fx.property_a.id)
    admin = login("admin@hvh.test")
    res = admin.patch(url, json={"code": "NEW"})
    assert res.status_code == 400
    assert admin.patch(url, json={"currency": "EUROS"}).status_code == 400
    assert admin.patch(url, json={"name": "x" * 201}).status_code == 400
    assert admin.patch(url, json={"settings": {"sla_minutes": 1}}).status_code == 400
    with database.session() as db:
        assert db.get(Property, fx.property_a.id).code == fx.property_a.code


def test_settings_capability_and_tenant_gates(app, fx, login):
    url = _settings_url(fx.property_a.id)
    for email in ("agent@hvh.test", "manager@hvh.test", "engineer@hvh.test"):
        c = login(email)
        assert c.get(url).status_code == 200  # every member may read
        assert c.patch(url, json={"name": "Nope"}).status_code == 403
    assert login("corporate@hvh.test").patch(url, json={"brand": "Group"}).status_code == 200
    admin_a = login("admin@hvh.test")
    other = _settings_url(fx.property_b.id)
    assert admin_a.get(other).status_code == 403
    assert admin_a.patch(other, json={"name": "Hijacked"}).status_code == 403
