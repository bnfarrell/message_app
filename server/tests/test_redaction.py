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
