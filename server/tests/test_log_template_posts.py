"""Posting with a template: validation, value rows and the generated body (spec §2.2, §2.3)."""
import pytest
from sqlalchemy import select

from app.domain import log as log_domain
from app.domain import log_templates
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import LogEntryFieldValue, LogTemplate, Notification
from app.schemas.enums import LogFieldType, MentionTargetType
from app.schemas.log import (
    CreateLogEntryRequest,
    LogFieldValueIn,
    LogTemplateFieldIn,
    LogTemplatePatch,
    MentionRef,
)
from tests.log_template_helpers import field_ids, front_desk, make_template


def _post(db, fx, template, answers: dict, *, author=None, **kw):
    """`answers` maps a field label to its raw value."""
    ids = field_ids(db, template)
    return log_domain.create(db, fx.property_a.id, (author or fx.agent_a).id,
                             CreateLogEntryRequest(
                                 template_id=template.id,
                                 field_values=[LogFieldValueIn(field_id=ids[k], value=v)
                                               for k, v in answers.items()], **kw))


def _failure(db, fx, template, answers, **kw) -> dict:
    with pytest.raises(ValidationFailed) as e:
        _post(db, fx, template, answers, **kw)
    return e.value.details


def _values(db, entry_id):
    return db.scalars(select(LogEntryFieldValue).where(LogEntryFieldValue.log_entry_id == entry_id)
                      .order_by(LogEntryFieldValue.position)).all()


def test_a_templated_post_stores_one_snapshot_row_per_answered_field(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": 38, "Occupancy": "87.5",
                                  "Duty manager": "  Sam  "})
        db.flush()
        assert entry.template_id == t.id
        rows = _values(db, entry.id)
        assert [(r.label, r.field_type, r.text_value, r.number_value) for r in rows] == [
            ("Arrivals actual", LogFieldType.integer, None, 38.0),
            ("Occupancy", LogFieldType.percent, None, 87.5),
            ("Duty manager", LogFieldType.short_text, "Sam", None),  # trimmed
        ]  # ADR and Handover were left blank: no rows for them
        assert {r.property_id for r in rows} == {fx.property_a.id}


def test_the_body_is_the_field_summary_then_the_notes(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": "38", "Occupancy": 87, "ADR": "129.5"},
                      body="  Quiet night.  ")
        assert entry.body == ("Arrivals actual: 38\nOccupancy: 87%\nADR: 129.5\n\n"
                              "Quiet night.")
        bare = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 0})
        assert bare.body == "Arrivals actual: 1\nOccupancy: 0%"  # notes are optional


@pytest.mark.parametrize("answers,reason_by_label", [
    ({"Occupancy": 87}, {"Arrivals actual": "required"}),
    ({"Arrivals actual": "  ", "Occupancy": 87}, {"Arrivals actual": "required"}),  # blank
    ({"Arrivals actual": "twelve", "Occupancy": 87}, {"Arrivals actual": "not_a_number"}),
    ({"Arrivals actual": "12.5", "Occupancy": 87}, {"Arrivals actual": "not_whole"}),
    ({"Arrivals actual": 12, "Occupancy": 100.5}, {"Occupancy": "out_of_range"}),
    ({"Arrivals actual": 12, "Occupancy": -1}, {"Occupancy": "out_of_range"}),
    ({"Arrivals actual": 12, "Occupancy": 87, "Duty manager": "x" * 201},
     {"Duty manager": "too_long"}),
    # Every failure is reported at once, each keyed by its own field.
    ({"Arrivals actual": "12.5", "Occupancy": 101},
     {"Arrivals actual": "not_whole", "Occupancy": "out_of_range"}),
])
def test_each_bad_answer_is_a_400_naming_its_field(database, fx, answers, reason_by_label):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        assert _failure(db, fx, t, answers) == {ids[k]: v for k, v in reason_by_label.items()}


def test_a_percent_of_exactly_0_or_100_and_a_whole_float_integer_are_fine(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        assert _post(db, fx, t, {"Arrivals actual": 12.0, "Occupancy": 100}).body.startswith(
            "Arrivals actual: 12\nOccupancy: 100%")


def test_not_a_number_and_infinity_are_not_numbers(database, fx):
    """float() parses both; neither is a reading anyone meant (review focus 2)."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        for raw in ("nan", "inf", "-Infinity"):
            assert _failure(db, fx, t, {"Arrivals actual": 1, "ADR": raw, "Occupancy": 5}) == {
                ids["ADR"]: "not_a_number"}


def test_a_huge_integer_that_overflows_float_is_a_400_not_a_500(database, fx):
    """`float()` raises `OverflowError`, not `ValueError`, on an integer this large -- a
    ~400-digit JSON number is otherwise an unhandled 500 (final review finding 2)."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        assert _failure(db, fx, t, {"Arrivals actual": int("9" * 400), "Occupancy": 5}) == {
            ids["Arrivals actual"]: "not_a_number"}


def test_a_number_too_big_for_the_column_is_a_400_not_a_postgres_overflow(database, fx):
    """number_value is Numeric(10, 2). PostgreSQL raises on 10**8 — a 500 — where SQLite
    stores it, so the domain must refuse it on both (review focus 1)."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        assert _failure(db, fx, t, {"Arrivals actual": 100_000_000, "Occupancy": 5}) == {
            ids["Arrivals actual"]: "out_of_range"}
        ok = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5, "ADR": 99_999_999.99})
        assert "ADR: 99999999.99" in ok.body


def test_a_value_that_only_overflows_after_rounding_is_still_refused(database, fx):
    """Fix round 1, review focus 1: 99999999.996 rounds to 100000000.0, which overflows
    Numeric(10, 2) on PostgreSQL. The limit must be checked against the rounded value, not
    the raw one, on both sides of zero."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        for raw in ("99999999.996", "-99999999.996"):
            assert _failure(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5, "ADR": raw}) == {
                ids["ADR"]: "out_of_range"}
        ok = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5, "ADR": "99999999.99"})
        assert "ADR: 99999999.99" in ok.body


def test_a_decimal_is_rounded_to_what_the_column_keeps(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5, "ADR": "129.456"})
        db.flush()
        assert "ADR: 129.46" in entry.body
        assert [r.number_value for r in _values(db, entry.id)][2] == 129.46


def test_unknown_duplicate_and_soft_deleted_field_ids_are_refused(database, fx):
    """Review focus 5: a stale composer answering a field the admin has since removed."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        other = make_template(db, fx, name="Other")
        stranger = field_ids(db, other)["Occupancy"]
        assert _failure(db, fx, t, {}) == {ids["Arrivals actual"]: "required",
                                           ids["Occupancy"]: "required"}
        with pytest.raises(ValidationFailed) as e:
            log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
                template_id=t.id, field_values=[
                    LogFieldValueIn(field_id=ids["Arrivals actual"], value=1),
                    LogFieldValueIn(field_id=ids["Arrivals actual"], value=2),
                    LogFieldValueIn(field_id=ids["Occupancy"], value=5),
                    LogFieldValueIn(field_id=stranger, value=5)]))
        assert e.value.details == {ids["Arrivals actual"]: "duplicate",
                                   stranger: "unknown_field"}
        # Soft-delete ADR; answering it afterwards is answering an unknown field.
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(fields=[
            LogTemplateFieldIn(id=ids["Arrivals actual"], label="Arrivals actual",
                               field_type="integer"),
            LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy", field_type="percent")]))
        with pytest.raises(ValidationFailed) as e:
            log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
                template_id=t.id, field_values=[
                    LogFieldValueIn(field_id=ids["Arrivals actual"], value=1),
                    LogFieldValueIn(field_id=ids["Occupancy"], value=5),
                    LogFieldValueIn(field_id=ids["ADR"], value=3)]))
        assert e.value.details == {ids["ADR"]: "unknown_field"}


def test_a_template_with_nothing_answered_and_no_notes_is_refused(database, fx):
    with database.session() as db:
        t = make_template(db, fx, fields=[LogTemplateFieldIn(label="Walk-ins",
                                                             field_type="integer",
                                                             required=False)])
        with pytest.raises(ValidationFailed, match="needs a body"):
            _post(db, fx, t, {})


def test_the_combined_body_must_fit(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        with pytest.raises(ValidationFailed) as e:
            _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5}, body="x" * 3990)
        assert e.value.details == {"body": "too_long"}


def test_mentions_in_the_notes_still_notify(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        token = f"@[Eli Engineer](user:{fx.engineer_a.id})"
        _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5}, body=f"{token} boiler noise",
              mentions=[MentionRef(type=MentionTargetType.user, id=fx.engineer_a.id)])
        db.flush()
        n = db.scalar(select(Notification).where(Notification.user_id == fx.engineer_a.id,
                                                 Notification.type == "log.mention"))
        assert n is not None and "@Eli Engineer boiler noise" in n.body


def test_template_lookup_audience_and_active_are_enforced(database, fx):
    """Review focus 5: a template deactivated while the composer was open is a clean 400."""
    with database.session() as db:
        t = make_template(db, fx, audience=front_desk(fx))
        answers = {"Arrivals actual": 1, "Occupancy": 5}
        with pytest.raises(Forbidden):
            _post(db, fx, t, answers, author=fx.engineer_a)
        _post(db, fx, t, answers, author=fx.manager_a)  # exempt role
        db.get(LogTemplate, t.id).active = False
        db.flush()
        assert _failure(db, fx, t, answers) == {"templateId": "inactive"}
        b = LogTemplate(property_id=fx.property_b.id, name="B", position=0,
                        created_by_user_id=fx.admin_b.id)
        db.add(b)
        db.flush()
        with pytest.raises(NotFound):
            log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                              CreateLogEntryRequest(template_id=b.id))


def test_field_values_without_a_template_are_refused(database, fx):
    with database.session() as db, pytest.raises(ValidationFailed) as e:
        log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
            body="hi", field_values=[LogFieldValueIn(field_id="x", value=1)]))
    assert e.value.details == {"fieldValues": "no_template"}


def test_a_free_form_post_still_needs_a_body(database, fx):
    with database.session() as db, pytest.raises(ValidationFailed, match="needs a body"):
        log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest())
