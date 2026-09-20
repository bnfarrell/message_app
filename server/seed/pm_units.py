"""The maintainable-unit rows the seeder inserts and the sample CSV carries (PM spec §9).

One source, two outputs, so they can never disagree: `seed.seed` inserts these rows, and
`seed.write_sample_csv` writes them in the import format for practising the load. The guest
rooms are exactly the stay grid the seeder already generates (floors 1–6 × 01–20), so every
seeded stay's room_number resolves to a unit.
"""
from __future__ import annotations

# PMS room-type codes for seed.data.ROOM_TYPES, in that order.
ROOM_TYPE_CODES = {
    "King": "KNGN",
    "Queen": "KWHN",
    "Double Queen": "TQNN",
    "Suite": "KSTE",
    "Accessible King": "KACC",
}

COMMON_AREAS: list[tuple[str, str, int | None]] = [
    ("LOBBY", "Lobby", 1),
    ("POOL", "Pool", 1),
    ("FITNESS", "Fitness Room", 2),
    ("LAUNDRY", "Guest Laundry", 2),
    ("BOILER-RM", "Boiler Room", 0),
    ("ELEV-A", "Elevator A", None),
    ("ELEV-B", "Elevator B", None),
    ("STAIR-N", "Stairwell North", None),
    ("STAIR-S", "Stairwell South", None),
    ("DOCK", "Loading Dock", 0),
]

EQUIPMENT: list[tuple[str, str]] = [
    ("POOL-PUMP-1", "Pool pump 1"),
    ("BOILER-1", "Boiler 1"),
    ("BOILER-2", "Boiler 2"),
    ("ICE-2F", "Ice machine 2F"),
    ("ICE-4F", "Ice machine 4F"),
    ("ELEV-MOTOR-A", "Elevator motor A"),
    ("ELEV-MOTOR-B", "Elevator motor B"),
    ("RTU-1", "Rooftop HVAC unit 1"),
]


def _room_type(floor: int, n: int) -> str:
    """Deterministic and plausible: accessible kings by the lifts on 1, corner suites on 6,
    the rest rotating through king / queen / double queen."""
    if floor == 1 and n <= 4:
        return ROOM_TYPE_CODES["Accessible King"]
    if floor == 6 and n in (1, 20):
        return ROOM_TYPE_CODES["Suite"]
    return (ROOM_TYPE_CODES["King"], ROOM_TYPE_CODES["Queen"],
            ROOM_TYPE_CODES["Double Queen"])[n % 3]


def unit_rows() -> list[dict]:
    rows: list[dict] = []
    for floor in range(1, 7):
        for n in range(1, 21):
            code = f"{floor}{n:02d}"
            rows.append({"code": code, "kind": "guest_room", "name": f"Room {code}",
                         "floor": floor, "room_type": _room_type(floor, n), "external_id": None})
    for code, name, floor in COMMON_AREAS:
        rows.append({"code": code, "kind": "common_area", "name": name, "floor": floor,
                     "room_type": None, "external_id": None})
    for code, name in EQUIPMENT:
        rows.append({"code": code, "kind": "equipment", "name": name, "floor": None,
                     "room_type": None, "external_id": None})
    return rows
