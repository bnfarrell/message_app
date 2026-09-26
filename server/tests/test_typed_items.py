"""The typed-item rules PM and shift checklists share (checklists spec §2.2)."""
from types import SimpleNamespace

import pytest

from app.domain import typed_items
from app.errors import ValidationFailed
from app.schemas.enums import PmItemType
from app.schemas.pm import AnswerPatch


def item(item_type, **kw):
    base = dict(id="i1", label="Pool pH", item_type=item_type, unit=None, min_value=None,
                max_value=None, required=True)
    base.update(kw)
    return SimpleNamespace(**base)


def answer():
    return SimpleNamespace(bool_value=None, text_value=None, number_value=None,
                           out_of_range=False, answered_at=None)


def test_number_answer_flags_out_of_range_exclusive_of_the_bounds():
    it = item(PmItemType.number, min_value=7.2, max_value=7.8)
    a = answer()
    typed_items.apply_answer(it, a, AnswerPatch(number_value=7.8))
    assert (a.number_value, a.out_of_range) == (7.8, False)
    assert a.answered_at is not None  # a unit test: the clock is not frozen here
    typed_items.apply_answer(it, a, AnswerPatch(number_value=8.1))
    assert a.out_of_range is True
    typed_items.apply_answer(it, a, AnswerPatch(number_value=None))
    assert (a.out_of_range, a.answered_at) == (False, None)


def test_text_is_trimmed_and_blank_means_unanswered():
    a = answer()
    typed_items.apply_answer(item(PmItemType.text), a, AnswerPatch(text_value="   "))
    assert (a.text_value, a.answered_at) == (None, None)


def test_the_wrong_field_for_the_type_is_refused():
    with pytest.raises(ValidationFailed):
        typed_items.apply_answer(item(PmItemType.checkbox), answer(),
                                 AnswerPatch(number_value=1))


def test_a_photo_item_cannot_be_answered_by_patch():
    with pytest.raises(ValidationFailed):
        typed_items.apply_answer(item(PmItemType.photo), answer(), AnswerPatch(bool_value=True))


def test_is_answered_per_type():
    a = answer()
    assert typed_items.is_answered(item(PmItemType.checkbox), a, set()) is False
    a.bool_value = False
    assert typed_items.is_answered(item(PmItemType.checkbox), a, set()) is False  # must be ticked
    a.bool_value = True
    assert typed_items.is_answered(item(PmItemType.checkbox), a, set()) is True
    assert typed_items.is_answered(item(PmItemType.photo), answer(), {"i1"}) is True
    assert typed_items.is_answered(item(PmItemType.photo), answer(), set()) is False


def test_out_of_range_title_names_the_reading_and_where():
    it = item(PmItemType.number, unit="", min_value=7.2, max_value=7.8)
    a = answer()
    a.number_value = 8.1
    assert typed_items.out_of_range_title(it, a, "Engineering AM Rounds") == \
        "Pool pH 8.1 out of range (7.2–7.8) — Engineering AM Rounds"
