"""Cold-start launcher for local development.

Creates `data/`, migrates the database to head, seeds it only if it's empty, then starts the dev
server with the job worker and SLA sweep running (`START_WORKER=1`). Safe to run twice: it checks
for existing data before seeding, so a second run never re-seeds on top of the first.

Used by `../start.bat` (Windows double-click) via `python dev_start.py`; also runnable directly
from anywhere with `python server/dev_start.py` or, from `server/`, `python dev_start.py`.

Deliberately does NOT `os.chdir()` into `server/`: Flask's debug reloader respawns this exact
process (`sys.orig_argv`, fixed at interpreter start) as a *new* process whose cwd is inherited
from whatever this one's cwd is at that moment — so if we'd chdir'd first, the relative script
path in that respawn command would resolve against the wrong directory and fail to launch. Instead
every path this module touches is made absolute, anchored at `SERVER_DIR`.
"""
from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
SEEDED_EMAIL = "ava@hvh.test"
SEEDED_PASSWORD = "Password123!"
_SQLITE_PREFIX = "sqlite:///"


def ensure_data_dir() -> None:
    (SERVER_DIR / "data").mkdir(parents=True, exist_ok=True)


def resolve_database_url(database_url: str) -> str:
    """Anchor a relative sqlite URL at `SERVER_DIR` so it resolves the same regardless of the
    process's current working directory. Non-sqlite and already-absolute URLs pass through."""
    if not database_url.startswith(_SQLITE_PREFIX):
        return database_url
    raw_path = database_url[len(_SQLITE_PREFIX):]
    path = Path(raw_path)
    if path.is_absolute():
        return database_url
    return _SQLITE_PREFIX + (SERVER_DIR / path).resolve().as_posix()


def is_db_empty(database_url: str) -> bool:
    """True if the database has no `property` table yet, or the table has no rows."""
    from sqlalchemy import inspect, select

    from app.db import Database
    from app.models import Property

    db = Database(database_url)
    try:
        if Property.__tablename__ not in inspect(db.engine).get_table_names():
            return True
        with db.session() as session:
            return session.scalar(select(Property.id).limit(1)) is None
    finally:
        db.engine.dispose()


def prepare(database_url: str):
    """Ensure `data/`, migrate to head, and seed only if empty.

    Returns (seeded, summary_or_None)."""
    from app.db import run_migrations

    ensure_data_dir()
    run_migrations(database_url)
    if not is_db_empty(database_url):
        return False, None
    from seed.seed import run as seed_run

    summary = seed_run(database_url, reset=False)
    return True, summary


def main() -> int:
    os.environ["START_WORKER"] = "1"

    from app.config import Config

    cfg = Config.from_env()
    cfg = dataclasses.replace(cfg, DATABASE_URL=resolve_database_url(cfg.DATABASE_URL))

    print(f"Preparing {cfg.DATABASE_URL} ...")
    seeded, summary = prepare(cfg.DATABASE_URL)
    if seeded:
        print(f"Seeded {summary.properties} properties, {summary.users} users, "
              f"{summary.guests} guests, "
              f"{summary.stays} stays, {summary.conversations} conversations, "
              f"{summary.messages} messages, "
              f"{summary.work_orders} work orders.")
    else:
        print("Database already has data — skipping seed.")

    port = int(os.getenv("PORT", "5000"))
    print(f"\nStarting server at http://127.0.0.1:{port}")
    print(f"Log in as {SEEDED_EMAIL} / {SEEDED_PASSWORD}\n")

    from app import create_app

    app = create_app(cfg)
    app.run(host="127.0.0.1", port=port, debug=not cfg.is_production, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
