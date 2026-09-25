"""Real SMS wire: Twilio Programmable Messaging. Same contract as MockSmsAdapter; everything
above it (consent, queueing, retry, the forward-only delivery-status invariant) is shared."""
from __future__ import annotations

from collections.abc import Mapping

from flask import Request
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.channels.base import InboundMessage, SendResult
from app.models import Message, Property
from app.schemas.enums import Channel

STATUS_CALLBACK_PATH = "/api/hooks/sms/status"


class TwilioSmsAdapter:
    channel = Channel.sms
    supports_rich_media = False
    max_length = 1600

    def __init__(self, account_sid: str, auth_token: str, public_base_url: str, *, client=None):
        self._client = client or Client(account_sid, auth_token)
        self._validator = RequestValidator(auth_token)
        self._public_base_url = public_base_url.rstrip("/")

    def send(self, db: Session, to: str, body: str, *, message_id: str) -> SendResult:
        msg = db.get(Message, message_id)
        prop = db.get(Property, msg.property_id)
        created = self._client.messages.create(
            from_=prop.sms_number, to=to, body=body,
            status_callback=self._public_base_url + STATUS_CALLBACK_PATH)
        return SendResult(provider_message_id=created.sid)

    def verify_inbound(self, request: Request) -> bool:
        # Twilio signs the URL it was configured with. Behind Railway's proxy Flask sees
        # http://<internal host>, so rebuild the URL from PUBLIC_BASE_URL rather than trust
        # request.url — that mismatch is the classic reason signature checks fail in production.
        url = self._public_base_url + request.path
        if request.query_string:
            url += "?" + request.query_string.decode()
        signature = request.headers.get("X-Twilio-Signature", "")
        return self._validator.validate(url, request.form.to_dict(), signature)

    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage:
        return InboundMessage(
            from_=payload.get("From", "").strip(),
            to=payload.get("To", "").strip(),
            body=(payload.get("Body") or "").strip(),
            provider_message_id=payload["MessageSid"],
        )
