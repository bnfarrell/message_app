"""Copy a local SQLite database into a Postgres one, table by table.

This is not a file copy and cannot be. SQLite has no real boolean, datetime, JSON or
enum types — it stores them as integers and strings — while Postgres enforces all four.
So the copy goes through the application's own SQLAlchemy metadata: reading applies each
column's result processor, writing applies its bind processor, and the type decorators
this project already defines (enum_type, UTCDateTime, JSON) do the conversion.

Tables are copied in foreign-key dependency order, which `metadata.sorted_tables` gives
us. Primary keys here are application-generated strings rather than serial integers, so
there are no sequences to reset afterwards.

Usage:

    # 1. Create the schema on the target first. This script never issues DDL.
    DATABASE_URL='postgresql+psycopg://…' alembic upgrade head

    # 2. Dry run — reports what it would copy and verifies both ends.
    python -m tools.sqlite_to_postgres --target 'postgresql+psycopg://…' --dry-run

    # 3. For real.
    python -m tools.sqlite_to_postgres --target 'postgresql+psycopg://…'

By default `user_session` and `job` are SKIPPED: sessions are live dev login cookies and
jobs are queue state belonging to the machine that produced them. Pass --include-ephemeral
if you really want them.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.engine import Engine

import app.models  # noqa: F401  -- importing registers every table on Base.metadata
from app.db import Base

# Rows that describe the *state of a running process* rather than the hotel's data.
# Copying sessions hands a production database a set of dev login cookies; copying jobs
# hands its worker a queue another machine already half-processed.
EPHEMERAL = {"user_session", "job"}


def _counts(engine: Engine, tables) -> dict[str, int]:
    with engine.connect() as conn:
        return {t.name: conn.execute(select(func.count()).select_from(t)).scalar_one()
                for t in tables}


def copy(source_url: str, target_url: str, *, include_ephemeral: bool, dry_run: bool,
         batch: int = 500) -> int:
    source = create_engine(source_url)
    target = create_engine(target_url)

    tables = [t for t in Base.metadata.sorted_tables
              if include_ephemeral or t.name not in EPHEMERAL]
    skipped = sorted({t.name for t in Base.metadata.sorted_tables} - {t.name for t in tables})

    # Fail before writing anything if the target schema is missing — a half-migrated
    # target would otherwise fail partway through and leave a mess.
    with target.connect() as conn:
        missing = [t.name for t in tables if not conn.dialect.has_table(conn, t.name)]
    if missing:
        sys.exit(f"target is missing {len(missing)} table(s): {', '.join(missing)}\n"
                 f"run `alembic upgrade head` against the target first")

    src_counts = _counts(source, tables)
    tgt_counts = _counts(target, tables)

    non_empty = {n: k for n, k in tgt_counts.items() if k}
    if non_empty and not dry_run:
        sys.exit("target is not empty: " + ", ".join(f"{n}={k}" for n, k in non_empty.items())
                 + "\nthis script only ever appends; clear the target or copy into a fresh one")

    total = 0
    for table in tables:
        rows_expected = src_counts[table.name]
        if not rows_expected:
            continue
        print(f"  {table.name:28} {rows_expected}")
        total += rows_expected
        if dry_run:
            continue
        with source.connect() as src, target.begin() as dst:
            result = src.execution_options(stream_results=True).execute(select(table))
            while chunk := result.fetchmany(batch):
                dst.execute(insert(table), [dict(row._mapping) for row in chunk])

    if skipped:
        print(f"\nskipped (pass --include-ephemeral to copy): {', '.join(skipped)}")

    if not dry_run:
        after = _counts(target, tables)
        wrong = {n: (src_counts[n], after[n]) for n in src_counts if src_counts[n] != after[n]}
        if wrong:
            sys.exit("row counts do not match after copy: "
                     + ", ".join(f"{n} {a}->{b}" for n, (a, b) in wrong.items()))
        print(f"\nverified: {total} rows across {len([t for t in tables if src_counts[t.name]])} "
              f"tables, counts match")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="sqlite:///data/app.db")
    parser.add_argument("--target", required=True, help="Postgres URL (SQLAlchemy form)")
    parser.add_argument("--include-ephemeral", action="store_true",
                        help=f"also copy {', '.join(sorted(EPHEMERAL))}")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.target.startswith("sqlite"):
        sys.exit("--target looks like SQLite; this copies INTO Postgres")

    print(f"source {args.source}\ntarget {args.target.split('@')[-1]}\n")
    copy(args.source, args.target, include_ephemeral=args.include_ephemeral,
         dry_run=args.dry_run)


if __name__ == "__main__":
    main()
