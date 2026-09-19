"""Hotel log (spec §3, §4, §6). Domain-level here; route-level assertions arrive in Task 8."""
import pytest
from sqlalchemy import select

from app import clock
from app.domain import log as log_domain
from app.errors import ValidationFailed
from app.models import Department, LogEntryMention, Notification, UserAccount
from app.schemas.enums import MentionTargetType, Shift, UserStatus
from app.schemas.log import CreateLogEntryRequest, MentionRef


def _req(**kw):
    kw.setdefault("body", "Handover note.")
    return CreateLogEntryRequest(**kw)


def test_create_stores_shift_and_mentions_in_order(database, fx):
    with database.session() as db:
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(mentions=[MentionRef(type=MentionTargetType.department,
                                      id=fx.dept_housekeeping.id),
                           MentionRef(type=MentionTargetType.user, id=fx.engineer_a.id)]),
        )
        db.flush()
        # conftest freezes 2026-09-10 12:00 UTC = 08:00 in America/New_York.
        assert entry.shift == Shift.am
        rows = db.scalars(
            select(LogEntryMention)
            .where(LogEntryMention.log_entry_id == entry.id)
            .order_by(LogEntryMention.position)
        ).all()
        assert [(r.type, r.target_id) for r in rows] == [
            (MentionTargetType.department, fx.dept_housekeeping.id),
            (MentionTargetType.user, fx.engineer_a.id),
        ]


def test_department_mention_notifies_each_member_once_and_never_the_author(database, fx):
    with database.session() as db:
        # The author is in front desk; mention front desk AND the author directly.
        log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(mentions=[MentionRef(type=MentionTargetType.department,
                                      id=fx.dept_front_desk.id),
                           MentionRef(type=MentionTargetType.user, id=fx.agent_a2.id)]),
        )
        db.flush()
        rows = db.scalars(select(Notification)
                          .where(Notification.type == "log.mention")).all()
        recipients = [n.user_id for n in rows]
        assert fx.agent_a.id not in recipients, "author must never be notified"
        assert recipients.count(fx.agent_a2.id) == 1, "mentioned twice, notified once"


def test_ack_expected_snapshots_active_department_members_excluding_author(database, fx):
    from app.models import PropertyMembership

    with database.session() as db:
        # A second active housekeeper, so the assertion below is about a real denominator
        # and not vacuously true of an always-empty list.
        other = db.scalar(select(PropertyMembership).where(
            PropertyMembership.user_id == fx.agent_a2.id,
            PropertyMembership.property_id == fx.property_a.id))
        other.department_id = fx.dept_housekeeping.id
        db.flush()
        entry = log_domain.create(
            db, fx.property_a.id, fx.housekeeper_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.department,
                                          id=fx.dept_housekeeping.id)]),
        )
        db.flush()
        assert fx.agent_a2.id in entry.ack_expected, "an active member must be expected"
        assert fx.housekeeper_a.id not in entry.ack_expected, "the author must not be"
        assert entry.requires_ack is True


def test_disabled_users_are_excluded_from_the_snapshot(database, fx):
    with database.session() as db:
        db.get(UserAccount, fx.engineer_a.id).status = UserStatus.disabled
        db.flush()
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.department,
                                          id=fx.dept_engineering.id)]),
        )
        db.flush()
        assert fx.engineer_a.id not in entry.ack_expected


def test_an_empty_resolved_audience_downgrades_requires_ack(database, fx):
    with database.session() as db:
        # housekeeper_a is the only active housekeeping member, and is the author.
        entry = log_domain.create(
            db, fx.property_a.id, fx.housekeeper_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.user,
                                          id=fx.housekeeper_a.id)]),
        )
        db.flush()
        assert entry.requires_ack is False
        assert entry.ack_expected == []


def test_a_cross_property_mention_is_rejected(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed):
            log_domain.create(
                db, fx.property_a.id, fx.agent_a.id,
                _req(mentions=[MentionRef(type=MentionTargetType.user, id=fx.agent_b.id)]),
            )


def test_a_whitespace_only_body_is_rejected(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed):
            log_domain.create(db, fx.property_a.id, fx.agent_a.id, _req(body="   \n\t  "))


def test_a_cross_property_department_tag_is_rejected(database, fx):
    with database.session() as db:
        other = fx.property_b.id
        dept_b = db.scalar(select(Department.id).where(Department.property_id == other))
        with pytest.raises(ValidationFailed):
            log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                              _req(department_id=dept_b))


def test_feed_is_newest_first_and_paginates_on_the_cursor(database, fx):
    from app.schemas.log import LogFeedQuery

    with database.session() as db:
        for i in range(3):
            log_domain.create(db, fx.property_a.id, fx.agent_a.id, _req(body=f"note {i}"))
            clock.advance(minutes=1)
        db.flush()
        page = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery())
        assert [e.body for e in page.entries] == ["note 2", "note 1", "note 0"]


def test_shift_and_department_filters(database, fx):
    from app.schemas.log import LogFeedQuery

    with database.session() as db:
        log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                          _req(body="tagged", department_id=fx.dept_housekeeping.id))
        log_domain.create(db, fx.property_a.id, fx.agent_a.id, _req(body="untagged"))
        db.flush()
        tagged = log_domain.feed(db, fx.property_a.id, fx.agent_a.id,
                                 LogFeedQuery(department_id=fx.dept_housekeeping.id))
        assert [e.body for e in tagged.entries] == ["tagged"]
        am = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery(shift=Shift.am))
        assert len(am.entries) == 2
        pm = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery(shift=Shift.pm))
        assert pm.entries == []


def test_mentioning_me_matches_direct_and_department_mentions(database, fx):
    from app.schemas.log import LogFeedQuery

    with database.session() as db:
        log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                          _req(body="direct",
                               mentions=[MentionRef(type=MentionTargetType.user,
                                                    id=fx.engineer_a.id)]))
        log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                          _req(body="via dept",
                               mentions=[MentionRef(type=MentionTargetType.department,
                                                    id=fx.dept_engineering.id)]))
        log_domain.create(db, fx.property_a.id, fx.agent_a.id, _req(body="unrelated"))
        db.flush()
        mine = log_domain.feed(db, fx.property_a.id, fx.engineer_a.id,
                               LogFeedQuery(mentioning_me=True))
        assert {e.body for e in mine.entries} == {"direct", "via dept"}


def test_the_feed_never_leaks_another_property(database, fx):
    from app.schemas.log import LogFeedQuery

    with database.session() as db:
        log_domain.create(db, fx.property_b.id, fx.agent_b.id, _req(body="B only"))
        db.flush()
        page = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery())
        assert page.entries == []


def test_entry_out_reports_ack_progress_for_the_viewer(database, fx):
    with database.session() as db:
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.user,
                                          id=fx.engineer_a.id)]))
        db.flush()
        seen_by_engineer = log_domain.get_out(db, fx.property_a.id, fx.engineer_a.id, entry.id)
        assert seen_by_engineer.ack_expected_count == 1
        assert seen_by_engineer.can_ack is True
        assert seen_by_engineer.acked_by_me is False
        assert [p.user_id for p in seen_by_engineer.outstanding] == [fx.engineer_a.id]
        seen_by_author = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        assert seen_by_author.can_ack is False
