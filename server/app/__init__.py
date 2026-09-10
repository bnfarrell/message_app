from __future__ import annotations

from flask import Flask

from app.config import Config
from app.errors import register_error_handlers


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    app = Flask(__name__)
    app.config["APP"] = config
    app.config["TESTING"] = config.TESTING
    app.config["SECRET_KEY"] = config.SESSION_SECRET

    from app.db import Database

    app.extensions["db"] = Database(config.DATABASE_URL)

    register_error_handlers(app)

    from app.api import auth, health

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
    return app
