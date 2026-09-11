from __future__ import annotations

from flask import Flask, request

from app.config import Config
from app.errors import register_error_handlers


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    app = Flask(__name__)
    app.config["APP"] = config
    app.config["TESTING"] = config.TESTING
    app.config["SECRET_KEY"] = config.SESSION_SECRET

    if not config.is_production:
        import email_validator

        # RFC 2606 reserved test domains (e.g. "hvh.test") back every seeded demo account;
        # email-validator otherwise rejects them as "special-use", which would make a freshly
        # seeded dev database impossible to log into (tests/conftest.py sets this same flag
        # for the test process). Never enabled in production.
        email_validator.TEST_ENVIRONMENT = True

    from app.db import Database

    app.extensions["db"] = Database(config.DATABASE_URL)

    from app.channels import registry as channel_registry

    channel_registry.install(app, config)

    register_error_handlers(app)

    from app.cli import seed_command

    app.cli.add_command(seed_command)

    from app.api import (
        analytics,
        assets,
        auth,
        categories,
        conversations,
        departments,
        guests,
        health,
        hooks,
        notifications,
        quick_replies,
        short_links,
        users,
        work_orders,
    )

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(departments.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(guests.bp)
    app.register_blueprint(notifications.bp)
    app.register_blueprint(conversations.bp)
    app.register_blueprint(work_orders.bp)
    app.register_blueprint(quick_replies.bp)
    app.register_blueprint(assets.bp)
    app.register_blueprint(categories.bp)
    app.register_blueprint(short_links.bp)
    app.register_blueprint(hooks.bp)
    app.register_blueprint(analytics.bp)

    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin")
        if origin and origin == config.CORS_ORIGIN:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Mock-Secret"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return resp

    if not config.is_production:
        from app.api import dev

        dev.install_event_recorder()
        app.register_blueprint(dev.bp)

    import os

    from app.queue import jobs as _jobs
    from app.queue.worker import Worker

    _jobs.RECURRING["pms.tick"] = config.PMS_TICK_SECONDS or 0
    if not config.PMS_TICK_SECONDS:
        _jobs.RECURRING.pop("pms.tick", None)
    app.extensions["worker"] = Worker(app)

    from app.queue.handlers import pms as pms_handler

    app.extensions["pms_adapter"] = pms_handler.adapter
    under_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if config.START_WORKER and (under_reloader or config.is_production):
        with app.extensions["db"].session() as db:
            for job_type in _jobs.RECURRING:
                _jobs.ensure_recurring(db, job_type)
        app.extensions["worker"].start()

    from app.realtime.ws import sock, start_sweeper

    sock.init_app(app)
    if config.START_WORKER and (under_reloader or config.is_production):
        start_sweeper(app)
    return app
