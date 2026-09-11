"""Fake SMS wire. Everything above it — consent, queueing, delivery status, retry — is real."""
from __future__ import annotations

import hmac
import uuid
from collections.abc import Mapping
from datetime import timedelta

from flask import Request
from sqlalchemy.orm import Session

from app import clock
from app.channels.base import InboundMessage, SendResult
from app.queue import jobs
from app.schemas.enums import Channel

FAIL_SUFFIX = "0000"
FAIL_CODE = "30007"
FAIL_MESSAGE = "Carrier violation (mock)"


class MockSmsAdapter:
    channel = Channel.sms
    supports_rich_media = False
    max_length = 1600

    def __init__(self, secret: str = "dev"):
        self.secret = secret

    def send(self, db: Session, to: str, body: str, *, message_id: str) -> SendResult:
        provider_id = f"mock-{uuid.uuid4().hex[:12]}"
        now = clock.now()
        if to.endswith(FAIL_SUFFIX):
            jobs.enqueue(db, "mock.delivery_status",
                         {"message_id": message_id, "status": "failed",
                          "error_code": FAIL_CODE, "error_message": FAIL_MESSAGE},
                         run_at=now + timedelta(milliseconds=400), max_attempts=1)
        else:
            jobs.enqueue(db, "mock.delivery_status", {"message_id": message_id, "status": "sent"},
                         run_at=now + timedelta(milliseconds=400), max_attempts=1)
            jobs.enqueue(db, "mock.delivery_status",
                         {"message_id": message_id, "status": "delivered"},
                         run_at=now + timedelta(milliseconds=1200), max_attempts=1)
        return SendResult(provider_message_id=provider_id)

    def verify_inbound(self, request: Request) -> bool:
        given = request.headers.get("X-Mock-Secret", "")
        return hmac.compare_digest(given, self.secret)

    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage:
        return InboundMessage(
            from_=payload.get("From", "").strip(),
            to=payload.get("To", "").strip(),
            body=(payload.get("Body") or "").strip(),
            provider_message_id=payload.get("MessageSid") or f"mock-in-{uuid.uuid4().hex[:12]}",
        )
