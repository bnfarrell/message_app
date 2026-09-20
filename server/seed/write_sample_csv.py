"""Writes fixtures/maintainable_units.sample.csv from seed.pm_units.unit_rows().

`python -m seed.write_sample_csv` from server/. tests/test_pm_sample_csv.py fails when the
committed file is stale, the same guard web/src/api/schema.json has.
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

from seed.pm_units import unit_rows

COLUMNS = ("code", "kind", "name", "floor", "room_type", "external_id")
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "fixtures" / "maintainable_units.sample.csv"


def render() -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in unit_rows():
        writer.writerow({k: "" if row[k] is None else row[k] for k in COLUMNS})
    return buf.getvalue()


def main(out: str | None = None) -> None:
    path = Path(out or DEFAULT_OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
