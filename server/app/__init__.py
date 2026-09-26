from __future__ import annotations

from flask import Flask, request

from app.config import INSECURE_SESSION_SECRETS, Config
from app.errors import register_error_handlers


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    if config.is_production and config.SESSION_SECRET in INSECURE_SESSION_SECRETS:
        # Refuse to boot rather than sign every session cookie with a secret that is published in
        # this repository.
        raise RuntimeError("SESSION_SECRET is still the placeholder value; set a real secret "
                           "before running with FLASK_ENV=production")
    app = Flask(__name__)
    app.config["APP"] = config
    app.config["TESTING"] = config.TESTING
    app.config["SECRET_KEY"] = config.SESSION_SECRET

    if not config.is_production or config.ALLOW_TEST_EMAIL_DOMAINS:
        import email_validator

        # RFC 2606 reserved test domains (e.g. "hvh.test") back every seeded demo account;
        # email-validator otherwise rejects them as "special-use", which would make a freshly
        # seeded dev database impossible to log into (tests/conftest.py sets this same flag
        # for the test process). In production this needs ALLOW_TEST_EMAIL_DOMAINS,
        # which a demo deployment seeded with the fixture must set or nobody can log in.
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
        checklists,
        conversations,
        departments,
        guests,
        health,
        hooks,
        housekeeping,
        log,
        maintainable_units,
        notifications,
        pm,
        properties,
        quick_replies,
        short_links,
        staff_messages,
        users,
        work_orders,
    )

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(departments.bp)
    app.register_blueprint(properties.bp)
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
    app.register_blueprint(staff_messages.bp)
    app.register_blueprint(staff_messages.directory_bp)
    app.register_blueprint(log.bp)
    app.register_blueprint(log.templates_bp)
    app.register_blueprint(maintainable_units.bp)
    app.register_blueprint(pm.bp)
    app.register_blueprint(housekeeping.bp)
    app.register_blueprint(checklists.bp)

    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin")
        if origin and origin == config.CORS_ORIGIN:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Mock-Secret"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return resp

    if config.dev_endpoints_enabled:
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
    # Start the worker exactly once per deployment. Under the Werkzeug reloader create_app runs
    # in both the parent monitor process and the child, and only the child should start it; with
    # no reloader there is only one process and it must. This asks USE_RELOADER (set by the dev
    # entrypoints that actually pass debug=True) rather than is_production, so that forgetting
    # FLASK_ENV cannot silently mean "nothing is being delivered" — and so that the switch
    # controlling job delivery is not also the switch controlling guest-data exposure
    # (config.dev_endpoints_enabled).
    under_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if config.START_WORKER and (under_reloader or not config.USE_RELOADER):
        with app.extensions["db"].session() as db:
            for job_type in _jobs.RECURRING:
                _jobs.ensure_recurring(db, job_type)
        app.extensions["worker"].start()

    from app.realtime.ws import sock, start_sweeper

    sock.init_app(app)
    if config.START_WORKER and (under_reloader or not config.USE_RELOADER):
        start_sweeper(app)

    from app import spa

    # No-op unless WEB_DIST names a built client, which only the container image does.
    # Registered last so the API and socket rules already exist when the catch-all lands.
    spa.install(app)
    return app
