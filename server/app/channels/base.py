from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from flask import Request
from sqlalchemy.orm import Session

from app.schemas.enums import Channel


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str


@dataclass(frozen=True)
class InboundMessage:
    from_: str
    to: str
    body: str
    provider_message_id: str


class ChannelAdapter(Protocol):
    channel: Channel
    supports_rich_media: bool
    max_length: int

    def send(self, db: Session, to: str, body: str, *, message_id: str) -> SendResult: ...

    def verify_inbound(self, request: Request) -> bool: ...

    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage: ...
