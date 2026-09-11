import pytest

from app.domain import consent
from app.errors import ConsentError
from app.models import Guest
from app.schemas.enums import SmsConsentStatus


@pytest.mark.parametrize("body,expected", [
    ("STOP", "stop"), ("stop", "stop"), ("stop.", "stop"), ("STOP .", "stop"), (" STOP ", "stop"),
    ("STOPALL", "stop"),
    ("UNSUBSCRIBE", "stop"), ("CANCEL", "stop"), ("END", "stop"), ("QUIT", "stop"),
    ("START", "start"), ("UNSTOP", "start"), ("YES", "start"),
    ("HELP", "help"),
    # Whole-message matching (CTIA/carrier convention): a keyword embedded in a real
    # message must NOT misfire as an opt-out/opt-in/help request.
    (" Stop please ", None),
    ("help me", None),
    ("Please stop the AC noise", None),
    ("Can you help with towels?", None),
    ("Stop by room 400 later", None),
    ("Yes, extra towels please", None),
    ("", None),
])
def test_classify_keyword(body, expected):
    assert consent.classify_keyword(body) == expected


def test_opt_out_and_opt_in_record_source_and_time(app, fx, database):
    from app import clock

    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        consent.opt_out(db, g, "sms_keyword")
        assert g.sms_consent_status == SmsConsentStatus.opted_out
        assert g.sms_consent_source == "sms_keyword"
        assert g.sms_consent_at == clock.now()
        consent.opt_in(db, g, "sms_keyword")
        assert g.sms_consent_status == SmsConsentStatus.opted_in


def test_assert_can_send_blocks_opted_out_unless_confirmation(app, fx, database):
    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        consent.assert_can_send(g)
        consent.opt_out(db, g, "sms_keyword")
        with pytest.raises(ConsentError) as ei:
            consent.assert_can_send(g)
        assert ei.value.code == "CONSENT_OPTED_OUT"
        consent.assert_can_send(g, allow_opt_out_confirmation=True)  # the one exception
