from flask import Flask, current_app

from app.channels.base import ChannelAdapter
from app.channels.mock_sms import MockSmsAdapter
from app.config import Config


def build_sms_adapter(config: Config) -> ChannelAdapter:
    if config.SMS_ADAPTER == "mock":
        return MockSmsAdapter(secret=config.MOCK_SMS_SECRET)
    raise ValueError(f"Unknown SMS_ADAPTER {config.SMS_ADAPTER!r}; Phase 1 supports 'mock'")


def install(app: Flask, config: Config) -> None:
    app.extensions["sms_adapter"] = build_sms_adapter(config)


def get_sms_adapter() -> ChannelAdapter:
    return current_app.extensions["sms_adapter"]
