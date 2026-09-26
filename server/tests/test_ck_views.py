"""Read models (checklists spec §4.2; plan clarification 4)."""
from datetime import UTC, datetime, timedelta

from app import clock
from app.domain import ck_instances, ck_photos, ck_views
from app.schemas.checklists import ChecklistInstanceQuery, ChecklistMissedQuery
from app.schemas.enums import ChecklistStatus, Role
from app.schemas.pm import AnswerPatch
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

THU = 1 << 3

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def test_list_rows_progress_and_shift_order(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        pm_t = make_template(db, fx, name="PM Walk", shift="pm")
        am_t = make_template(db, fx, name="AM Rounds", shift="am")
        am, _ = ck_instances.ensure_instance(db, am_t, today)
        ck_instances.ensure_instance(db, pm_t, today)
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, am.id)
        answer = next(a for a in ck_views.detail(db, pid, am.id).answers)
        ck_instances.save_answer(db, pid, fx.engineer_a.id, Role.dept_staff, am.id, answer.id,
                                 AnswerPatch(bool_value=True))
        rows = ck_views.list_instances(db, pid, ChecklistInstanceQuery())
        assert [r.template_name for r in rows] == ["AM Rounds", "PM Walk"]
        assert (rows[0].done, rows[0].total, rows[0].assigned_name) == (1, 4, "Eli Engineer")
        assert (rows[1].done, rows[1].total, rows[1].status) == (0, 4, ChecklistStatus.open)


def test_list_filters_by_department(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        ck_instances.ensure_instance(db, make_template(db, fx), today)
        ck_instances.ensure_instance(db, make_template(
            db, fx, name="Desk Opening", department_id=fx.dept_front_desk.id), today)
        rows = ck_views.list_instances(db, pid, ChecklistInstanceQuery(
            department_id=fx.dept_front_desk.id))
        assert [r.template_name for r in rows] == ["Desk Opening"]


def test_list_without_department_filter_shows_all(database, fx):
    """Review focus 4: people with no department see every department's checklists."""
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        ck_instances.ensure_instance(db, make_template(db, fx), today)
        ck_instances.ensure_instance(db, make_template(
            db, fx, name="Desk Opening", department_id=fx.dept_front_desk.id), today)
        assert len(ck_views.list_instances(db, pid, ChecklistInstanceQuery())) == 2


def test_detail_carries_items_answers_photos_and_missing(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        inst, _ = ck_instances.ensure_instance(db, make_template(db, fx), today)
        before = ck_views.detail(db, pid, inst.id)
        assert (len(before.items), before.answers, before.missing_required) == (4, [], [])
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        photo_item = next(i for i in before.items if i.item_type.value == "photo")
        ck_photos.attach(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id, data=PNG,
                         item_id=photo_item.id)
        after = ck_views.detail(db, pid, inst.id)
        assert len(after.answers) == 4 and len(after.photos) == 1
        assert after.photos[0].url.endswith(f"/photos/{after.photos[0].id}")
        assert photo_item.id not in after.missing_required and len(after.missing_required) == 2


def test_missed_lists_the_last_n_days_newest_first(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        t = make_template(db, fx)
        for back in (1, 3, 10):
            inst, _ = ck_instances.ensure_instance(db, t, today - timedelta(days=back))
            inst.status = ChecklistStatus.missed
        db.flush()
        rows = ck_views.missed(db, pid, ChecklistMissedQuery(days=7))
        assert [r.due_date for r in rows] == [today - timedelta(days=1),
                                             today - timedelta(days=3)]


def test_missed_seven_days_includes_today_minus_six_excludes_minus_seven(database, fx):
    """Finding 5: "last 7 days" is 7 local dates including today, so back=6 is the boundary
    that is still in range and back=7 is just outside it."""
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        t = make_template(db, fx)
        for back in (6, 7):
            inst, _ = ck_instances.ensure_instance(db, t, today - timedelta(days=back))
            inst.status = ChecklistStatus.missed
        db.flush()
        rows = ck_views.missed(db, pid, ChecklistMissedQuery(days=7))
        assert [r.due_date for r in rows] == [today - timedelta(days=6)]


def test_list_default_day_is_the_hotel_day_not_the_calendar_date(database, fx):
    """Critical finding 1: FROZEN clock is Thu 2026-09-10 12:00 UTC = Thu 08:00 New York. An
    overnight instance due Thursday is still live at Fri 02:00 New York (06:00 UTC) — after
    local midnight but before the AM boundary — so the default day must follow the hotel's
    current shift day, not the calendar date `local_today` would give (which has already
    rolled to Friday)."""
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        t = make_template(db, fx, name="Night Watch", shift="overnight", weekdays=THU)
        ck_instances.ensure_instance(db, t, today)
    clock.freeze(datetime(2026, 9, 11, 6, 0, tzinfo=UTC))  # Fri 02:00 New York
    with database.session() as db:
        rows = ck_views.list_instances(db, pid, ChecklistInstanceQuery())
        assert [r.template_name for r in rows] == ["Night Watch"]
