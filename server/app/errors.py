from __future__ import annotations

from typing import Any

from flask import Flask, jsonify
from pydantic import ValidationError
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
    status = 422
    code = "CONSENT_OPTED_OUT"


class RateLimited(AppError):
    status = 429
    code = "RATE_LIMITED"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(e: AppError):
        return jsonify(e.to_body()), e.status

    @app.errorhandler(ValidationError)
    def _pydantic_error(e: ValidationError):
        return jsonify(ValidationFailed("Invalid request", details=e.errors()).to_body()), 400

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        code = (e.name or "error").upper().replace(" ", "_")
        return jsonify({"error": {"code": code, "message": e.description}}), e.code or 500
