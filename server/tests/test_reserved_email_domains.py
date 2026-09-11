"""A production deployment seeded with the fixture must still be loggable-into.

The seed uses RFC 2606 reserved domains (hvh.test, lsi.test, group.test). Pydantic's
EmailStr rejects those as special-use, and the escape hatch used to be keyed purely on
"not production" — so seeding a production database succeeded and then every login 400'd.
"""
import email_validator
import pytest

from app import create_app
from app.config import Config


@pytest.fixture(autouse=True)
def _restore_flag():
    before = email_validator.TEST_ENVIRONMENT
    yield
    email_validator.TEST_ENVIRONMENT = before


def _config(**kwargs) -> Config:
    return Config(SESSION_SECRET="a-real-secret-for-this-test", TESTING=True, **kwargs)


def test_development_allows_reserved_domains_without_asking():
    email_validator.TEST_ENVIRONMENT = False
    create_app(_config(ENV="development"))
    assert email_validator.TEST_ENVIRONMENT is True


def test_production_rejects_them_by_default():
    email_validator.TEST_ENVIRONMENT = False
    create_app(_config(ENV="production"))
    # Still false: a real deployment must not silently accept unroutable addresses.
    assert email_validator.TEST_ENVIRONMENT is False


def test_production_allows_them_only_when_explicitly_opted_in():
    email_validator.TEST_ENVIRONMENT = False
    create_app(_config(ENV="production", ALLOW_TEST_EMAIL_DOMAINS=True))
    assert email_validator.TEST_ENVIRONMENT is True


def test_the_flag_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("ALLOW_TEST_EMAIL_DOMAINS", "1")
    assert Config.from_env().ALLOW_TEST_EMAIL_DOMAINS is True
    monkeypatch.setenv("ALLOW_TEST_EMAIL_DOMAINS", "0")
    assert Config.from_env().ALLOW_TEST_EMAIL_DOMAINS is False
    monkeypatch.delenv("ALLOW_TEST_EMAIL_DOMAINS")
    assert Config.from_env().ALLOW_TEST_EMAIL_DOMAINS is False


def test_a_seeded_address_actually_validates_under_the_flag():
    from pydantic import TypeAdapter

    from app.schemas.auth import LoginRequest

    email_validator.TEST_ENVIRONMENT = False
    create_app(_config(ENV="production", ALLOW_TEST_EMAIL_DOMAINS=True))
    # The address the seed actually creates for the admin account.
    parsed = TypeAdapter(LoginRequest).validate_python(
        {"email": "alex@hvh.test", "password": "Password123!"})
    assert parsed.email == "alex@hvh.test"
