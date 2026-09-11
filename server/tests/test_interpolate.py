from app.domain.quick_replies import interpolate


def test_interpolates_known_variables():
    out = interpolate("Hi {{guest_first_name}}, room {{room_number}} at {{property_name}}.",
                      {"guest_first_name": "Sarah", "room_number": "412",
                       "property_name": "Harbourview"})
    assert out == "Hi Sarah, room 412 at Harbourview."


def test_missing_values_fall_back_gracefully():
    out = interpolate("Hi {{guest_first_name}}, checkout {{departure_date}}.",
                      {"guest_first_name": None, "departure_date": None})
    assert out == "Hi there, checkout soon."


def test_unknown_variables_are_left_visible():
    assert interpolate("x {{nope}} y", {}) == "x {{nope}} y"


def test_whitespace_inside_braces_is_tolerated():
    assert interpolate("Hi {{ guest_first_name }}", {"guest_first_name": "Diego"}) == "Hi Diego"
