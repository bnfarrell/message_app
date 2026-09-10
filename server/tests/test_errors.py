from app.errors import AppError


def test_code_override_derives_matching_default_message():
    err = AppError(code="CUSTOM_THING")
    body = err.to_body()
    assert body["error"]["code"] == "CUSTOM_THING"
    assert body["error"]["message"] == "Custom thing"
