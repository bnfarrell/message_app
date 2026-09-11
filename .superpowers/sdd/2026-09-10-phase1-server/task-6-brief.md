### Task 6: Pure domain utilities — SMS segments, card redaction, quick-reply interpolation

**Files:**
- Create: `server/app/domain/sms.py`, `server/app/domain/redaction.py`, `server/app/domain/quick_replies.py` (interpolation only; CRUD arrives in Task 16), `server/tests/test_sms.py`, `server/tests/test_redaction.py`, `server/tests/test_interpolate.py`

**Interfaces:**
- Produces: `sms.segment_count(body) -> int`, `sms.is_gsm7(body) -> bool`; `redaction.redact(body) -> tuple[str, bool]`; `quick_replies.interpolate(body, ctx: dict[str, str | None]) -> str` with keys `guest_first_name, room_number, property_name, agent_first_name, departure_date`; `quick_replies.VARIABLES`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_sms.py`:
```python
import pytest

from app.domain.sms import is_gsm7, segment_count


@pytest.mark.parametrize("body,expected", [
    ("", 0),
    ("Hi", 1),
    ("a" * 160, 1),
    ("a" * 161, 2),
    ("a" * 306, 2),
    ("a" * 307, 3),
    ("Café " + "a" * 155, 1),          # é is in the GSM-7 basic set
    ("€" * 80, 1),                      # € is a GSM-7 extension char: counts double -> 160 septets
    ("€" * 81, 2),
    ("Hello 😊", 1),                    # emoji forces UCS-2: 70 per single segment
    ("😊" * 35, 1),                     # 35 emoji = 70 UTF-16 code units
    ("😊" * 36, 2),
    ("你好" * 34, 2),                    # 68 units UCS-2: 67 per segment when multipart
])
def test_segment_count(body, expected):
    assert segment_count(body) == expected


def test_is_gsm7():
    assert is_gsm7("Hello, room 412 is ready @ 3pm!")
    assert not is_gsm7("Hello — dash")  # em dash is not GSM-7
```

`server/tests/test_redaction.py`:
```python
from app.domain.redaction import redact


def test_redacts_valid_card_with_spaces():
    body, flagged = redact("my card is 4242 4242 4242 4242 thanks")
    assert flagged is True
    assert body == "my card is **** **** **** 4242 thanks"


def test_redacts_valid_card_with_dashes_and_plain():
    assert redact("5555-5555-5555-4444")[0] == "**** **** **** 4444"
    assert redact("378282246310005")[0] == "**** **** **** 0005"  # 15-digit Amex


def test_leaves_luhn_invalid_numbers_alone():
    body, flagged = redact("call 1234 5678 9012 3456")
    assert flagged is False and body == "call 1234 5678 9012 3456"


def test_leaves_phone_numbers_and_reservation_ids_alone():
    assert redact("my number is +1 555 123 4567")[1] is False
    assert redact("reservation 48213377")[1] is False


def test_redacts_multiple_occurrences():
    body, flagged = redact("4242424242424242 and 4000056655665556")
    assert flagged and body == "**** **** **** 4242 and **** **** **** 5556"
```

`server/tests/test_interpolate.py`:
```python
from app.domain.quick_replies import interpolate


def test_interpolates_known_variables():
    out = interpolate("Hi {{guest_first_name}}, room {{room_number}} at {{property_name}}.",
                      {"guest_first_name": "Sarah", "room_number": "412", "property_name": "Harbourview"})
    assert out == "Hi Sarah, room 412 at Harbourview."


def test_missing_values_fall_back_gracefully():
    out = interpolate("Hi {{guest_first_name}}, checkout {{departure_date}}.",
                      {"guest_first_name": None, "departure_date": None})
    assert out == "Hi there, checkout soon."


def test_unknown_variables_are_left_visible():
    assert interpolate("x {{nope}} y", {}) == "x {{nope}} y"


def test_whitespace_inside_braces_is_tolerated():
    assert interpolate("Hi {{ guest_first_name }}", {"guest_first_name": "Diego"}) == "Hi Diego"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_sms.py tests/test_redaction.py tests/test_interpolate.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `app/domain/sms.py`**

```python
"""SMS segment counting per GSM 03.38: 160/153 septets for GSM-7, 70/67 code units for UCS-2."""

GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = set("^{}\\[~]|€\f")


def is_gsm7(body: str) -> bool:
    return all(ch in GSM7_BASIC or ch in GSM7_EXTENDED for ch in body)


def _gsm7_septets(body: str) -> int:
    return sum(2 if ch in GSM7_EXTENDED else 1 for ch in body)


def _utf16_units(body: str) -> int:
    return len(body.encode("utf-16-le")) // 2


def segment_count(body: str) -> int:
    if not body:
        return 0
    if is_gsm7(body):
        n = _gsm7_septets(body)
        return 1 if n <= 160 else -(-n // 153)
    n = _utf16_units(body)
    return 1 if n <= 70 else -(-n // 67)
```

- [ ] **Step 4: Write `app/domain/redaction.py`**

```python
"""PCI: card numbers texted by guests are masked before storage (design.md §9.1)."""
import re

_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact(body: str) -> tuple[str, bool]:
    flagged = False

    def _sub(m: re.Match) -> str:
        nonlocal flagged
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            flagged = True
            return f"**** **** **** {digits[-4:]}"
        return m.group(0)

    return _CANDIDATE.sub(_sub, body), flagged
```

Only 13–19-digit Luhn-valid runs are masked; 10/11-digit phone numbers and 8-digit reservation ids never match.

- [ ] **Step 5: Write `app/domain/quick_replies.py` (interpolation half)**

```python
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
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): SMS segment counting, card-number redaction, quick-reply interpolation"
```

---

