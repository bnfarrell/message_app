from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


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
    TESTING: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

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
        )
