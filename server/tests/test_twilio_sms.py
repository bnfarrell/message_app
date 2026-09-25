from dataclasses import dataclass, field

import pytest
from twilio.request_validator import RequestValidator

from app.channels.twilio_sms import TwilioSmsAdapter
from app.config import Config
from app.schemas.enums import Direction
from tests.factories import make_conversation, make_message

TOKEN = "test-auth-token"
BASE = "https://relay.example.com"


@dataclass
class FakeMessages:
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Msg", (), {"sid": "SM_fake_sid"})()


@dataclass
class FakeClient:
    messages: FakeMessages = field(default_factory=FakeMessages)


def _adapter(client=None) -> TwilioSmsAdapter:
    return TwilioSmsAdapter(account_sid="ACxxx", auth_token=TOKEN, public_base_url=BASE,
                            client=client or FakeClient())


def test_send_uses_property_number_and_returns_twilio_sid(app, fx, database):
    client = FakeClient()
    with database.session() as db:
        from app.models import Guest

        guest = db.get(Guest, fx.guest_inhouse_a.id)
        conv = make_conversation(db, fx, guest)
        msg = make_message(db, conv, direction=Direction.outbound, body="Your room is ready")
        result = _adapter(client).send(db, "+15551234567", "Your room is ready", message_id=msg.id)
    assert result.provider_message_id == "SM_fake_sid"
    [call] = client.messages.calls
    assert call["from_"] == fx.property_a.sms_number
    assert call["to"] == "+15551234567"
    assert call["body"] == "Your room is ready"
    assert call["status_callback"] == f"{BASE}/api/hooks/sms/status"


def _signed_request(app, params: dict, *, sign_url: str, sign_params: dict | None = None):
    sig = RequestValidator(TOKEN).compute_signature(sign_url, sign_params or params)
    # Flask's test context speaks http://localhost; the signature is over the public URL Twilio
    # was configured with, which is exactly the mismatch a proxy introduces in production.
    return app.test_request_context("/api/hooks/sms/inbound", method="POST", data=params,
                                    headers={"X-Twilio-Signature": sig})


def test_verify_inbound_accepts_a_signature_over_the_public_url(app):
    params = {"From": "+15551234567", "To": "+15550100", "Body": "hi", "MessageSid": "SM1"}
    with _signed_request(app, params, sign_url=f"{BASE}/api/hooks/sms/inbound"):
        from flask import request

        assert _adapter().verify_inbound(request) is True


def test_verify_inbound_rejects_a_tampered_body(app):
    params = {"From": "+15551234567", "To": "+15550100", "Body": "hi", "MessageSid": "SM1"}
    with _signed_request(app, params, sign_url=f"{BASE}/api/hooks/sms/inbound",
                         sign_params={**params, "Body": "something else"}):
        from flask import request

        assert _adapter().verify_inbound(request) is False


def test_verify_inbound_rejects_a_missing_signature(app):
    with app.test_request_context("/api/hooks/sms/inbound", method="POST", data={"Body": "hi"}):
        from flask import request

        assert _adapter().verify_inbound(request) is False


def test_parse_inbound_reads_twilio_field_names(app):
    m = _adapter().parse_inbound({"From": "+15551234567", "To": "+15550100", "Body": " hi ",
                                  "MessageSid": "SM1"})
    assert ((m.from_, m.to, m.body, m.provider_message_id)
           == ("+15551234567", "+15550100", "hi", "SM1"))


def test_registry_builds_twilio_adapter_from_config():
    from app.channels.registry import build_sms_adapter

    cfg = Config(SMS_ADAPTER="twilio", TWILIO_ACCOUNT_SID="ACxxx", TWILIO_AUTH_TOKEN=TOKEN,
                 PUBLIC_BASE_URL=BASE)
    assert isinstance(build_sms_adapter(cfg), TwilioSmsAdapter)


@pytest.mark.parametrize("missing", ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL"])
def test_registry_refuses_twilio_without_credentials(missing):
    """Startup must fail loudly: a blank token would make every send fail at runtime and every
    webhook signature check fail silently, which looks like a dead number."""
    from app.channels.registry import build_sms_adapter

    values = {"TWILIO_ACCOUNT_SID": "ACxxx", "TWILIO_AUTH_TOKEN": TOKEN, "PUBLIC_BASE_URL": BASE}
    values[missing] = ""
    with pytest.raises(ValueError, match=missing):
        build_sms_adapter(Config(SMS_ADAPTER="twilio", **values))
