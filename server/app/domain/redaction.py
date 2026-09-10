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
