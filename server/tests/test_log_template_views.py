"""The read side: templated entries in the feed, the picker list and the admin list
(log templates spec §2.1, §3.2, §4.2)."""
from app.domain import log as log_domain
from app.domain import log_templates
from app.schemas.log import (
    CreateLogEntryRequest,
    LogFeedQuery,
    LogFieldValueIn,
    LogTemplateFieldIn,
    LogTemplatePatch,
)
from tests.log_template_helpers import field_ids, front_desk, make_template


def _post(db, fx, template, answers, body=""):
    ids = field_ids(db, template)
    entry = log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
        template_id=template.id, body=body,
        field_values=[LogFieldValueIn(field_id=ids[k], value=v) for k, v in answers.items()]))
    db.flush()
    return entry


def test_a_templated_entry_carries_its_template_values_and_notes(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": 38, "Occupancy": 87.5,
                                  "Handover": "Line one\n\nLine two"}, body="Quiet night.")
        out = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        assert (out.template.id, out.template.name) == (t.id, "Night Audit")
        assert [(v.label, v.field_type.value, v.text_value, v.number_value)
                for v in out.field_values] == [
            ("Arrivals actual", "integer", None, 38.0),
            ("Occupancy", "percent", None, 87.5),
            ("Handover", "long_text", "Line one\n\nLine two", None),
        ]
        # Review focus 3: the notes survive a long-text value that itself has a blank line.
        assert out.notes == "Quiet night."
        assert out.body.endswith("\n\nQuiet night.")


def test_notes_are_none_without_notes_and_on_free_form_posts(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        bare = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5})
        free = log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                                 CreateLogEntryRequest(body="Plain note"))
        db.flush()
        by_id = {e.id: e for e in log_domain.feed(db, fx.property_a.id, fx.agent_a.id,
                                                  LogFeedQuery()).entries}
        assert (by_id[bare.id].notes, by_id[bare.id].template.name) == (None, "Night Audit")
        assert (by_id[free.id].template, by_id[free.id].field_values,
                by_id[free.id].notes) == (None, [], None)


def test_editing_or_retiring_the_template_never_changes_a_past_post(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        entry = _post(db, fx, t, {"Arrivals actual": 38, "Occupancy": 87, "ADR": 120},
                      body="Notes stay.")
        before = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        # Rename one field, drop another, then retire the template.
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(fields=[
            LogTemplateFieldIn(id=ids["Arrivals actual"], label="Arrivals (actual)",
                               field_type="integer"),
            LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy", field_type="percent")]))
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                            LogTemplatePatch(active=False))
        after = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        assert after.field_values == before.field_values  # labels and values are snapshots
        assert (after.body, after.notes) == (before.body, "Notes stay.")
        assert after.template.name == "Night Audit"  # still named although retired


def test_the_picker_lists_usable_active_templates_current_shift_first(database, fx):
    """conftest freezes 2026-09-10 12:00 UTC = 08:00 in New York: the AM shift."""
    with database.session() as db:
        night = make_template(db, fx, name="Night Audit", shift="overnight")
        am = make_template(db, fx, name="AM Checklist", shift="am")
        general = make_template(db, fx, name="General", shift=None)
        make_template(db, fx, name="Retired", shift="am", active=False)
        make_template(db, fx, name="Engineering only", shift="am",
                      audience=[{"type": "department", "id": fx.dept_engineering.id}])
        names = [t.name for t in log_templates.list_usable(db, fx.property_a.id, fx.agent_a.id)]
        assert names == ["AM Checklist", "Night Audit", "General"]
        assert (am.position, night.position, general.position) == (1, 0, 2)
        # Fields ride along, active only, in order.
        first = log_templates.list_usable(db, fx.property_a.id, fx.agent_a.id)[0]
        assert [f.label for f in first.fields][:2] == ["Arrivals actual", "Occupancy"]


def test_a_non_audience_user_does_not_see_the_template_but_an_exempt_role_does(database, fx):
    with database.session() as db:
        make_template(db, fx, audience=front_desk(fx))
        assert log_templates.list_usable(db, fx.property_a.id, fx.engineer_a.id) == []
        assert [t.name for t in log_templates.list_usable(db, fx.property_a.id,
                                                          fx.manager_a.id)] == ["Night Audit"]


def test_the_admin_list_includes_inactive_templates_and_counts_their_posts(database, fx):
    with database.session() as db:
        used = make_template(db, fx, name="Night Audit")
        make_template(db, fx, name="Retired", active=False)
        for _ in range(3):
            _post(db, fx, used, {"Arrivals actual": 1, "Occupancy": 5})
        log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                          CreateLogEntryRequest(body="free-form posts count for nothing"))
        db.flush()
        rows = {t.name: t for t in log_templates.list_admin(db, fx.property_a.id)}
        assert (rows["Night Audit"].used_count, rows["Retired"].used_count) == (3, 0)
        assert rows["Retired"].active is False
        assert log_templates.list_admin(db, fx.property_b.id) == []
