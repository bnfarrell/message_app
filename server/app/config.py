from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Placeholder secrets that must never reach production: the dataclass default and the value
# shipped in .env.example, which is what a copied-and-forgotten .env contains.
INSECURE_SESSION_SECRETS = frozenset({"dev-secret-change-me", "change-me-in-production"})


def _optional_bool(raw: str | None) -> bool | None:
    return None if raw is None else raw == "1"


@dataclass
class Config:
    DATABASE_URL: str = "sqlite:///data/app.db"
    SESSION_SECRET: str = "dev-secret-change-me"
    MOCK_SMS_SECRET: str = "dev"
    SMS_ADAPTER: str = "mock"
    PMS_TICK_SECONDS: int = 90
    START_WORKER: bool = False
    CORS_ORIGIN: str = "http://localhost:5173"
    ENV: str = "development"
    ENABLE_DEV_ENDPOINTS: bool = False
    USE_RELOADER: bool = False
    SESSION_COOKIE_SECURE: bool | None = None
    TESTING: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def dev_endpoints_enabled(self) -> bool:
        """Positive opt-in, never in production.

        /api/dev/sim/* is unauthenticated and returns every guest at every property (names,
        E.164 phones, rooms, consent), so the unsafe state must not be reachable by forgetting an
        env var: it used to register whenever FLASK_ENV != "production", and ENV defaults to
        "development".
        """
        return self.ENABLE_DEV_ENDPOINTS and not self.is_production

    @property
    def cookie_secure(self) -> bool:
        """Secure by default in production; SESSION_COOKIE_SECURE overrides in either direction
        (a staging deployment behind plain HTTP, or local dev over an HTTPS tunnel)."""
        if self.SESSION_COOKIE_SECURE is None:
            return self.is_production
        return self.SESSION_COOKIE_SECURE

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()
        return cls(
            DATABASE_URL=os.getenv("DATABASE_URL", cls.DATABASE_URL),
            SESSION_SECRET=os.getenv("SESSION_SECRET", cls.SESSION_SECRET),
            MOCK_SMS_SECRET=os.getenv("MOCK_SMS_SECRET", cls.MOCK_SMS_SECRET),
            SMS_ADAPTER=os.getenv("SMS_ADAPTER", cls.SMS_ADAPTER),
            PMS_TICK_SECONDS=int(os.getenv("PMS_TICK_SECONDS", cls.PMS_TICK_SECONDS)),
            START_WORKER=os.getenv("START_WORKER", "0") == "1",
            CORS_ORIGIN=os.getenv("CORS_ORIGIN", cls.CORS_ORIGIN),
            ENV=os.getenv("FLASK_ENV", cls.ENV),
            ENABLE_DEV_ENDPOINTS=os.getenv("ENABLE_DEV_ENDPOINTS", "0") == "1",
            USE_RELOADER=os.getenv("USE_RELOADER", "0") == "1",
            SESSION_COOKIE_SECURE=_optional_bool(os.getenv("SESSION_COOKIE_SECURE")),
        )
