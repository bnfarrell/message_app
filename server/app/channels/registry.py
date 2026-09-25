from flask import Flask, current_app

from app.channels.base import ChannelAdapter
from app.channels.mock_sms import MockSmsAdapter
from app.channels.twilio_sms import TwilioSmsAdapter
from app.config import Config


def build_sms_adapter(config: Config) -> ChannelAdapter:
    if config.SMS_ADAPTER == "mock":
        return MockSmsAdapter(secret=config.MOCK_SMS_SECRET)
    if config.SMS_ADAPTER == "twilio":
        for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL"):
            if not getattr(config, name):
                raise ValueError(f"SMS_ADAPTER=twilio requires {name}")
        return TwilioSmsAdapter(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN,
                                config.PUBLIC_BASE_URL)
    raise ValueError(f"Unknown SMS_ADAPTER {config.SMS_ADAPTER!r}; expected 'mock' or 'twilio'")


def install(app: Flask, config: Config) -> None:
    app.extensions["sms_adapter"] = build_sms_adapter(config)


def get_sms_adapter() -> ChannelAdapter:
    return current_app.extensions["sms_adapter"]
