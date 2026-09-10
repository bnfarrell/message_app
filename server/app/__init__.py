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

    from app.channels import registry as channel_registry

    channel_registry.install(app, config)

    register_error_handlers(app)

    from app.api import auth, conversations, departments, health, hooks, notifications, users

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(departments.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(notifications.bp)
    app.register_blueprint(conversations.bp)
    app.register_blueprint(hooks.bp)

    import os

    from app.queue import jobs as _jobs
    from app.queue.worker import Worker

    _jobs.RECURRING["pms.tick"] = config.PMS_TICK_SECONDS or 0
    if not config.PMS_TICK_SECONDS:
        _jobs.RECURRING.pop("pms.tick", None)
    app.extensions["worker"] = Worker(app)
    under_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if config.START_WORKER and (under_reloader or config.is_production):
        with app.extensions["db"].session() as db:
            for job_type in _jobs.RECURRING:
                _jobs.ensure_recurring(db, job_type)
        app.extensions["worker"].start()
    return app
