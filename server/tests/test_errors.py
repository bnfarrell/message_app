from app.errors import AppError


def test_code_override_derives_matching_default_message():
    err = AppError(code="CUSTOM_THING")
    body = err.to_body()
    assert body["error"]["code"] == "CUSTOM_THING"
    assert body["error"]["message"] == "Custom thing"


def test_a_validation_400_does_not_echo_the_raw_input_back(app, fx, login):
    """Ruling D91. Pydantic's `input` key repeated whatever the caller typed, verbatim and in
    full, into an error body that nothing reads it from — the client's shared normaliser
    (web/src/api/fieldErrors.ts) takes the field from `loc` and the wording from `msg` and says
    in its own comment that `input` is deliberately ignored."""
    raw = "9" * 99  # smsNumber is capped at 32, so this is rejected before any domain code runs
    res = login("admin@hvh.test").patch(f"/api/p/{fx.property_a.id}/settings",
                                        json={"smsNumber": raw})
    assert res.status_code == 400
    body = res.get_json()
    assert raw not in res.get_data(as_text=True)
    entry = body["error"]["details"][0]
    assert "input" not in entry and "url" not in entry
    # The shape the client codes against is otherwise unchanged.
    assert entry["loc"] == ["smsNumber"] and entry["msg"] and entry["type"]


def test_a_query_validation_400_does_not_echo_the_raw_input_either(app, fx, login):
    raw = "not-a-number-" + "x" * 80
    res = login("agent@hvh.test").get(f"/api/p/{fx.property_a.id}/conversations?limit={raw}")
    assert res.status_code == 400
    assert raw not in res.get_data(as_text=True)
    assert "input" not in res.get_json()["error"]["details"][0]


def test_the_bare_pydantic_error_handler_strips_input_and_url(app):
    """errors.py's ValidationError handler is the third site: it called e.errors() with no
    arguments, so it leaked the raw input *and* a pydantic.dev documentation URL. It is reached
    only by a ValidationError escaping a view rather than by parse_body, so it is invoked
    directly here."""
    import pydantic

    from app.schemas.properties import PropertySettingsPatch

    handler = app.error_handler_spec[None][None][pydantic.ValidationError]
    raw = "z" * 99
    try:
        PropertySettingsPatch(smsNumber=raw)
    except pydantic.ValidationError as e:
        with app.test_request_context():
            response, status = handler(e)
        assert status == 400
        assert raw not in response.get_data(as_text=True)
        entry = response.get_json()["error"]["details"][0]
        assert "input" not in entry and "url" not in entry
    else:
        raise AssertionError("expected the over-length smsNumber to be rejected")
