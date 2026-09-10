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
