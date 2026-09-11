from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from flask import jsonify, request
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ValidationFailed


@contextmanager
def db_session() -> Iterator[Session]:
    with get_db().session() as db:
        yield db


def parse_body[M: BaseModel](model: type[M]) -> M:
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ValidationFailed("Invalid request body", details=e.errors(include_url=False)) from e


def parse_query[M: BaseModel](model: type[M]) -> M:
    try:
        return model.model_validate(request.args.to_dict())
    except ValidationError as e:
        raise ValidationFailed("Invalid query", details=e.errors(include_url=False)) from e


def serialize(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True)
    if isinstance(obj, list):
        return [serialize(o) for o in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    return obj


def ok(payload: Any, status: int = 200):
    return jsonify(serialize(payload)), status


def no_content():
    return "", 204


def client_meta() -> tuple[str | None, str | None]:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0] or None
    return ip, request.headers.get("User-Agent")
