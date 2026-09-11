from sqlalchemy import select

from app.models import Property
from tests.factories import inbound


def _settings_url(property_id: str) -> str:
    return f"/api/p/{property_id}/settings"


def test_get_settings_returns_the_whole_shape(app, fx, login):
    res = login("agent@hvh.test").get(_settings_url(fx.property_a.id))
    assert res.status_code == 200
    body = res.get_json()
    assert set(body) == {"id", "name", "code", "timezone", "address", "phone", "smsNumber",
                         "brand", "currency", "logoUrl", "primaryColor",
                         "slaMinutes", "autoResolveHours", "helpText"}
    assert body["id"] == fx.property_a.id
    assert body["code"] == fx.property_a.code
    assert "settings" not in body  # the bag itself is never exposed; its three live keys are
    assert (body["slaMinutes"], body["autoResolveHours"]) == (15, 4)
    assert "555 0100" in body["helpText"]


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
        assert p.settings["help_text"]  # untouched keys survive a patch of the column fields


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


def test_patch_settings_rejects_an_explicit_null_on_a_required_field(app, fx, database, login):
    """Ruling D82. `name`, `timezone` and `currency` are NOT NULL columns and slaMinutes /
    autoResolveHours are read back through `int(...)`, so a cleared form input serialised as null
    used to be an unhandled 500 (or, for the bag keys, a TypeError on the next inbound message)."""
    url = _settings_url(fx.property_a.id)
    admin = login("admin@hvh.test")
    for field in ("name", "timezone", "currency", "slaMinutes", "autoResolveHours"):
        res = admin.patch(url, json={field: None})
        assert res.status_code == 400, (field, res.status_code, res.get_json())
        err = res.get_json()["error"]
        assert err["code"] == "VALIDATION_FAILED" and err["details"] == {field: "required"}
    # the nullable neighbours are still clearable, which is what the form needs for empty inputs
    cleared = admin.patch(url, json={"address": None, "phone": None, "brand": None,
                                     "logoUrl": None, "primaryColor": None, "helpText": None})
    assert cleared.status_code == 200
    assert cleared.get_json()["address"] is None and cleared.get_json()["helpText"] is None
    with database.session() as db:
        assert db.get(Property, fx.property_a.id).name  # nothing was nulled by the rejections


def test_patch_settings_rejects_a_sender_number_that_would_break_inbound(app, fx, database, login):
    """Ruling D83: normalize_phone used to return "+" + digits for anything starting with "+", so
    "+" saved with a 200 and silently stopped inbound SMS for the property."""
    url = _settings_url(fx.property_a.id)
    admin = login("admin@hvh.test")
    for junk in ("+", "+1-", "+ "):
        assert admin.patch(url, json={"smsNumber": junk}).status_code == 400, junk
    assert admin.patch(url, json={"smsNumber": "+55512"}).get_json()["smsNumber"] == "+55512"
    with database.session() as db:
        assert db.get(Property, fx.property_a.id).sms_number == "+55512"  # short codes still work


def test_patch_sla_minutes_reaches_the_conversation_sla(app, fx, client, database, login):
    """`Property.settings` is a plain JSON column with no MutableDict, so the value has to be
    reassigned rather than mutated in place or the write never flushes."""
    from app.domain import conversations as conv_domain
    from app.models import Conversation

    url = _settings_url(fx.property_a.id)
    admin = login("admin@hvh.test")
    assert admin.patch(url, json={"slaMinutes": 0}).status_code == 400
    patched = admin.patch(url, json={"slaMinutes": 45, "autoResolveHours": 12}).get_json()
    assert (patched["slaMinutes"], patched["autoResolveHours"]) == (45, 12)
    assert admin.get(url).get_json() == patched

    with database.session() as db:  # a fresh session: proves it reached the database
        assert conv_domain.sla_minutes(db, fx.property_a.id) == 45
        assert conv_domain.auto_resolve_hours(db, fx.property_a.id) == 12

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    with database.session() as db:
        conv = db.scalar(select(Conversation).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        assert (conv.sla_due_at - conv.last_guest_message_at).total_seconds() == 45 * 60


def test_patch_help_text_changes_the_guest_visible_help_reply(app, fx, client, database, login):
    """help_text is the automatic reply to an SMS "HELP" — the one settings key a guest sees."""
    from app.models import Message
    from app.schemas.enums import Direction

    admin = login("admin@hvh.test")
    admin.patch(_settings_url(fx.property_a.id),
                json={"helpText": "Harbourview: text us, or call +1 555 0199."})
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "HELP")
    with database.session() as db:
        out = db.scalar(select(Message).where(Message.direction == Direction.outbound))
        assert out.body == "Harbourview: text us, or call +1 555 0199."
