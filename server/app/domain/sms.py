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
