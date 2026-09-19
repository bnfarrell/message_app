"""Hotel log (spec §3, §4, §6). Domain-level here; route-level assertions arrive in Task 8."""
import pytest
from sqlalchemy import select

from app import clock
from app.api.log import MULTIPART_OVERHEAD_BYTES
from app.domain import log as log_domain
from app.domain.work_orders import MAX_PHOTO_BYTES
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
                           MentionRef(type=MentionTargetType.user, id=fx.agent_a.id),
                           MentionRef(type=MentionTargetType.user, id=fx.agent_a2.id)]),
        )
        db.flush()
        rows = db.scalars(select(Notification)
                          .where(Notification.type == "log.mention")).all()
        recipients = [n.user_id for n in rows]
        assert fx.agent_a.id not in recipients, "author must never be notified"
        assert recipients.count(fx.agent_a2.id) == 1, "mentioned twice, notified once"


def test_a_mentioned_user_who_must_also_ack_is_notified_once(database, fx):
    with database.session() as db:
        log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(mentions=[MentionRef(type=MentionTargetType.user, id=fx.engineer_a.id)],
                 requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.user,
                                          id=fx.engineer_a.id)]))
        db.flush()
        rows = db.scalars(select(Notification).where(
            Notification.user_id == fx.engineer_a.id)).all()
        assert [n.type for n in rows] == ["log.mention"], \
            "mentioned AND expected must yield exactly one notification, the mention"


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
        assert fx.supervisor_a.id in entry.ack_expected, \
            "the remaining active member must still be expected"


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


def test_cursor_pagination_walks_every_entry_exactly_once_newest_first(database, fx, monkeypatch):
    from app.schemas.log import LogFeedQuery

    monkeypatch.setattr(log_domain, "FEED_PAGE_SIZE", 2)
    with database.session() as db:
        for i in range(5):
            log_domain.create(db, fx.property_a.id, fx.agent_a.id, _req(body=f"note {i}"))
            clock.advance(minutes=1)
        db.flush()

        seen: list[str] = []
        cursor = None
        for _ in range(10):
            page = log_domain.feed(db, fx.property_a.id, fx.agent_a.id,
                                   LogFeedQuery(cursor=cursor))
            seen.extend(e.body for e in page.entries)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        else:
            pytest.fail("feed did not terminate within 10 pages")

        assert seen == ["note 4", "note 3", "note 2", "note 1", "note 0"]
        assert page.next_cursor is None


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
        # engineer_a is NOT a member of housekeeping, so this must not match: proves the
        # filter is scoped to the viewer's own departments, not "any department mention".
        log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                          _req(body="other dept",
                               mentions=[MentionRef(type=MentionTargetType.department,
                                                    id=fx.dept_housekeeping.id)]))
        log_domain.create(db, fx.property_a.id, fx.agent_a.id, _req(body="unrelated"))
        db.flush()
        mine = log_domain.feed(db, fx.property_a.id, fx.engineer_a.id,
                               LogFeedQuery(mentioning_me=True))
        assert {e.body for e in mine.entries} == {"direct", "via dept"}


def test_the_feed_never_leaks_another_property(database, fx):
    from app.schemas.log import LogFeedQuery

    with database.session() as db:
        entry = log_domain.create(db, fx.property_b.id, fx.agent_b.id, _req(body="B only"))
        entry.pinned = True
        db.flush()
        page = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery())
        assert page.entries == []
        assert page.pinned == []


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


def test_acknowledging_twice_is_idempotent(database, fx):
    from app.models import AuditLog, LogEntryAck

    with database.session() as db:
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.user,
                                          id=fx.engineer_a.id)]))
        db.flush()
        log_domain.acknowledge(db, fx.property_a.id, fx.engineer_a.id, entry.id)
        log_domain.acknowledge(db, fx.property_a.id, fx.engineer_a.id, entry.id)
        db.flush()
        rows = db.scalars(select(LogEntryAck)
                          .where(LogEntryAck.log_entry_id == entry.id)).all()
        assert len(rows) == 1
        # Spec §9: the repeat must not duplicate AND must not re-audit. The unique
        # constraint on (log_entry_id, user_id) already guarantees the row count above;
        # this guarantees the audit trail (and the realtime event) aren't touched twice.
        audit_rows = db.scalars(select(AuditLog).where(
            AuditLog.action == "log_entry.acknowledged",
            AuditLog.entity_id == entry.id)).all()
        assert len(audit_rows) == 1, "a repeat acknowledgement must not re-audit"
        updated_events = [e for e in db.info.get("events", []) if e.type == "log.entry.updated"]
        assert len(updated_events) == 1, "a repeat acknowledgement must not re-fire the event"
        after = log_domain.get_out(db, fx.property_a.id, fx.engineer_a.id, entry.id)
        assert after.can_ack is False
        assert after.acked_by_me is True


def test_a_user_outside_the_audience_cannot_acknowledge(database, fx):
    from app.errors import Forbidden

    with database.session() as db:
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.user,
                                          id=fx.engineer_a.id)]))
        db.flush()
        with pytest.raises(Forbidden):
            log_domain.acknowledge(db, fx.property_a.id, fx.housekeeper_a.id, entry.id)


def test_joining_the_department_later_does_not_change_the_denominator(database, fx):
    from app.errors import Forbidden
    from app.models import PropertyMembership

    with database.session() as db:
        entry = log_domain.create(
            db, fx.property_a.id, fx.agent_a.id,
            _req(requires_ack=True,
                 ack_audience=[MentionRef(type=MentionTargetType.department,
                                          id=fx.dept_engineering.id)]))
        db.flush()
        before = len(entry.ack_expected)
        membership = db.scalar(select(PropertyMembership).where(
            PropertyMembership.user_id == fx.agent_a2.id,
            PropertyMembership.property_id == fx.property_a.id))
        membership.department_id = fx.dept_engineering.id
        db.flush()
        refreshed = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        assert refreshed.ack_expected_count == before
        with pytest.raises(Forbidden):
            log_domain.acknowledge(db, fx.property_a.id, fx.agent_a2.id, entry.id)


def test_pin_and_unpin_move_the_entry_in_and_out_of_the_pinned_block(database, fx):
    from app.models import AuditLog
    from app.schemas.log import LogFeedQuery

    with database.session() as db:
        entry = log_domain.create(db, fx.property_a.id, fx.agent_a.id, _req(body="pin me"))
        db.flush()
        log_domain.set_pinned(db, fx.property_a.id, fx.supervisor_a.id, entry.id, True)
        db.flush()
        page = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery())
        assert [e.body for e in page.pinned] == ["pin me"]
        # Still in the chronological feed too — the client renders both (spec §4.2).
        assert [e.body for e in page.entries] == ["pin me"]

        # A redundant pin by someone else must be a true no-op: it must not re-audit,
        # and it must not steal or clear credit for who actually pinned it.
        log_domain.set_pinned(db, fx.property_a.id, fx.manager_a.id, entry.id, True)
        db.flush()
        pin_audits = db.scalars(select(AuditLog).where(
            AuditLog.action == "log_entry.pinned", AuditLog.entity_id == entry.id)).all()
        assert len(pin_audits) == 1, "a redundant pin must not re-audit"
        assert entry.pinned_by_user_id == fx.supervisor_a.id, \
            "a redundant pin by someone else must not overwrite who pinned it"

        log_domain.set_pinned(db, fx.property_a.id, fx.supervisor_a.id, entry.id, False)
        db.flush()
        page2 = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery())
        assert page2.pinned == []


def test_post_and_list_through_the_api(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/log-entries"
    agent = login("agent@hvh.test")
    res = agent.post(base, json={"body": "AM checklist done.",
                                 "departmentId": fx.dept_front_desk.id})
    assert res.status_code == 201
    created = res.get_json()
    assert created["shift"] == "am"
    assert created["departmentName"]
    feed = agent.get(base).get_json()
    assert [e["id"] for e in feed["entries"]] == [created["id"]]
    assert feed["pinned"] == []


def test_an_agent_cannot_pin_but_a_supervisor_can(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/log-entries"
    agent = login("agent@hvh.test")
    entry_id = agent.post(base, json={"body": "pin me"}).get_json()["id"]
    assert agent.post(f"{base}/{entry_id}/pin").status_code == 403
    sup = login("supervisor@hvh.test")
    pinned = sup.post(f"{base}/{entry_id}/pin")
    assert pinned.status_code == 200
    assert pinned.get_json()["pinned"] is True
    assert sup.delete(f"{base}/{entry_id}/pin").get_json()["pinned"] is False


def test_photo_round_trips(app, fx, login):
    import io

    # sniff_image_type only inspects the magic bytes, so a valid signature is a
    # sufficient fixture. This mirrors the PNG constant in test_work_order_photos.py
    # rather than constructing a real encoded image.
    png = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"

    base = f"/api/p/{fx.property_a.id}/log-entries"
    agent = login("agent@hvh.test")
    res = agent.post(base, data={"body": "with photo",
                                 "photo": (io.BytesIO(png), "x.png", "image/png")},
                     content_type="multipart/form-data")
    assert res.status_code == 201, res.get_json()
    url = res.get_json()["photoUrl"]
    assert url
    got = agent.get(url)
    assert got.status_code == 200
    assert got.data == png
    assert got.headers["X-Content-Type-Options"] == "nosniff"
    assert got.headers["Content-Disposition"] == "inline"
    assert got.headers["Cache-Control"] == "private, max-age=86400"


def test_a_non_image_upload_is_rejected(app, fx, login):
    import io

    base = f"/api/p/{fx.property_a.id}/log-entries"
    agent = login("agent@hvh.test")
    # A real GIF: an image, but deliberately not an accepted one. Proves the check
    # is a signature allow-list rather than "does this look like any image at all".
    gif = b"GIF89a" + b"\x00" * 40
    res = agent.post(base, data={"body": "bad", "photo": (io.BytesIO(gif), "x.png", "image/png")},
                     content_type="multipart/form-data")
    # ValidationFailed is 400 in app/errors.py, NOT 422 — 422 is ConsentError only.
    # Assert the code and details too, matching test_work_order_photos.py's convention.
    assert res.status_code == 400, res.get_json()
    body = res.get_json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert body["details"] == {"photo": "unsupported_image_type"}


def test_an_oversized_body_is_refused_before_it_is_parsed(app, fx, login):
    """The Content-Length guard in front of parse_body, mirroring
    test_work_order_photos.py's test of the same name.

    Sends no `photo` part, only an oversized `junk` field, so this exercises the
    Content-Length check specifically rather than the byte check inside
    _photo_from_request. Without the guard, request.form is still never read cleanly:
    Werkzeug's own max_form_memory_size (500 KB per non-file field) rejects the huge
    `junk` value first, as a bare 413 with none of this API's error shape — proven by
    sabotaging the guard below. The guard's job is to produce this endpoint's own 400/
    VALIDATION_FAILED/file_too_large response before either limit is hit.
    """
    base = f"/api/p/{fx.property_a.id}/log-entries"
    agent = login("agent@hvh.test")
    res = agent.post(base, data={"junk": "x" * (MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES + 1)},
                     content_type="multipart/form-data")
    assert res.status_code == 400, res.get_json()
    assert res.get_json()["error"]["details"] == {"photo": "file_too_large"}


def test_a_multipart_photo_post_still_persists_a_mention(app, fx, login):
    """`request.form.to_dict()` yields strings for every field, so `mentions` arrives as a
    JSON-encoded string rather than a list when the composer attaches a photo. Without
    CreateLogEntryRequest's before-validator parsing that string, this combination fails
    validation and the mention is silently dropped.
    """
    import io
    import json

    png = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"

    base = f"/api/p/{fx.property_a.id}/log-entries"
    agent = login("agent@hvh.test")
    mentions = json.dumps([{"type": "user", "id": fx.engineer_a.id}])
    res = agent.post(base, data={"body": "with photo and a mention",
                                 "mentions": mentions,
                                 "photo": (io.BytesIO(png), "x.png", "image/png")},
                     content_type="multipart/form-data")
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["mentions"] == [
        {"type": "user", "id": fx.engineer_a.id, "displayName": "Eli Engineer"},
    ]


def test_mentionables_lists_people_and_departments(app, fx, login):
    agent = login("agent@hvh.test")
    rows = agent.get(f"/api/p/{fx.property_a.id}/log-entries/mentionables").get_json()
    kinds = {r["type"] for r in rows}
    assert kinds == {"user", "department"}
    assert fx.dept_housekeeping.id in [r["id"] for r in rows if r["type"] == "department"]


def test_no_route_can_change_an_entry_body(app, fx, login):
    """Spec §4.4 — immutability is a property of the route table, so assert on the map."""
    base = f"/api/p/{fx.property_a.id}/log-entries"
    agent = login("agent@hvh.test")
    entry_id = agent.post(base, json={"body": "original"}).get_json()["id"]
    assert agent.patch(f"{base}/{entry_id}", json={"body": "rewritten"}).status_code == 405
    assert agent.delete(f"{base}/{entry_id}").status_code == 405
    assert agent.get(f"{base}/{entry_id}").get_json()["body"] == "original"
