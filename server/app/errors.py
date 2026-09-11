from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flask import Flask, jsonify
from pydantic import ValidationError
from sqlalchemy.orm import Session
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str | None = None, *, details: Any = None, code: str | None = None):
        if code:
            self.code = code
        self.message = message or self.code.replace("_", " ").capitalize()
        self.details = details
        super().__init__(self.message)

    def to_body(self) -> dict:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            err["details"] = self.details
        return {"error": err}


class ValidationFailed(AppError):
    status = 400
    code = "VALIDATION_FAILED"


class Unauthorized(AppError):
    status = 401
    code = "UNAUTHORIZED"


class Forbidden(AppError):
    status = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status = 409
    code = "CONFLICT"


class TransitionError(AppError):
    status = 409
    code = "INVALID_TRANSITION"


class ConsentError(AppError):
    """Raised by consent.assert_can_send(). May carry `audit_write`: a callback that persists the
    compliance audit row on a fresh connection once the caller's own session has rolled back
    (see Database.session() in app.db) — never on the caller's own still-open session, which may
    already hold a write lock a nested write would deadlock against."""

    status = 422
    code = "CONSENT_OPTED_OUT"

    def __init__(self, message: str | None = None, *, details: Any = None, code: str | None = None,
                 audit_write: Callable[[Session], None] | None = None):
        super().__init__(message, details=details, code=code)
        self.audit_write = audit_write


class RateLimited(AppError):
    status = 429
    code = "RATE_LIMITED"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(e: AppError):
        return jsonify(e.to_body()), e.status

    @app.errorhandler(ValidationError)
    def _pydantic_error(e: ValidationError):
        # Same two arguments as _util.parse_body: no pydantic.dev URL, and no echo of the
        # caller's raw input, which nothing reads.
        details = e.errors(include_url=False, include_input=False)
        return jsonify(ValidationFailed("Invalid request", details=details).to_body()), 400

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        code = (e.name or "error").upper().replace(" ", "_")
        return jsonify({"error": {"code": code, "message": e.description}}), e.code or 500
