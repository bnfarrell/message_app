"""fixtures/maintainable_units.sample.csv is generated; it must match its source and import
cleanly (PM spec §9, §12 #1)."""
from pathlib import Path

from app.domain import pm_units
from seed.pm_units import unit_rows
from seed.write_sample_csv import DEFAULT_OUT, render


def test_unit_rows_are_the_stay_grid_plus_areas_and_equipment():
    rows = unit_rows()
    assert len(rows) == 138
    codes = [r["code"] for r in rows if r["kind"] == "guest_room"]
    assert codes[0] == "101" and codes[-1] == "620" and len(codes) == 120
    assert len(set(r["code"] for r in rows)) == 138, "codes are unique"


def test_committed_sample_csv_is_current():
    path = Path(DEFAULT_OUT)
    assert path.exists(), "run: python -m seed.write_sample_csv"
    assert path.read_text(encoding="utf-8") == render(), (
        "fixtures/maintainable_units.sample.csv is stale — re-run python -m seed.write_sample_csv")


def test_sample_csv_imports_cleanly_and_idempotently(database, fx):
    text = Path(DEFAULT_OUT).read_text(encoding="utf-8")
    with database.session() as db:
        first = pm_units.import_csv(db, fx.property_a.id, fx.admin_a.id, text)
        assert (first.created, first.updated, first.errors) == (138, 0, [])
        second = pm_units.import_csv(db, fx.property_a.id, fx.admin_a.id, text)
        assert (second.created, second.updated) == (0, 138)
