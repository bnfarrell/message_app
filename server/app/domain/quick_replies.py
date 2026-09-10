from __future__ import annotations

import re

VARIABLES = ("guest_first_name", "room_number", "property_name", "agent_first_name", "departure_date")
FALLBACKS = {
    "guest_first_name": "there",
    "room_number": "your room",
    "property_name": "the hotel",
    "agent_first_name": "the front desk",
    "departure_date": "soon",
}
_HOLE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def interpolate(body: str, ctx: dict[str, str | None]) -> str:
    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in VARIABLES:
            return m.group(0)
        value = ctx.get(key)
        return str(value) if value not in (None, "") else FALLBACKS[key]

    return _HOLE.sub(_sub, body)
