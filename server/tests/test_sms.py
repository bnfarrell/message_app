import json
from pathlib import Path

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
    ("你好" * 35, 1),                    # 70 units UCS-2: exactly one segment
    ("你好" * 36, 2),                    # 72 units UCS-2: multipart, 67 per segment
])
def test_segment_count(body, expected):
    assert segment_count(body) == expected


def test_is_gsm7():
    assert is_gsm7("Hello, room 412 is ready @ 3pm!")
    assert not is_gsm7("Hello — dash")  # em dash is not GSM-7


GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "sms-segments.json"


def _golden_cases():
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return [pytest.param(c, id=c["name"]) for c in doc["cases"]]


@pytest.mark.parametrize("case", _golden_cases())
def test_golden_vectors_match_the_shared_fixture(case):
    """Ruling D89. web/src/lib/segments.ts is a deliberate line-for-line port of app/domain/sms.py
    — the inbox composer needs per-keystroke feedback with no network round trip — so nothing but
    this fixture stops the two drifting. web/src/lib/segments.golden.test.ts asserts the same file;
    if either side moves, exactly one suite goes red and names the case.

    `characters` is `len(body)` (code points, what the API returns) rather than UTF-16 units: for
    a non-BMP character the two differ, and that is precisely where a port is most likely to slip.
    """
    body = case["body"]
    assert is_gsm7(body) is case["isGsm7"], case["why"]
    assert segment_count(body) == case["segments"], case["why"]
    assert len(body) == case["characters"], case["why"]


def test_the_golden_fixture_covers_the_boundaries():
    """A vector file is worth exactly what it covers, so require the cases that matter to exist:
    a pared-down fixture would make the guard above silently vacuous."""
    names = {c["name"] for c in json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]}
    assert {"empty", "gsm7-160", "gsm7-161", "gsm7-306", "gsm7-307",
            "gsm7-extension-crosses-160", "gsm7-extension-crosses-153",
            "ucs2-70", "ucs2-71", "ucs2-134", "ucs2-135",
            "emoji-alone", "emoji-crosses-70", "emoji-crosses-67"} <= names
