## Task 6: The feed query

**Files:**
- Modify: `server/app/domain/log.py`
- Test: `server/tests/test_log_api.py`

**Interfaces:**
- Consumes: `create` (Task 5); `LogFeedQuery`, `LogFeedOut`, `LogEntryOut` (Task 4)
- Produces:
  - `app.domain.log.feed(db, property_id, viewer_user_id, query: LogFeedQuery) -> LogFeedOut`
  - `app.domain.log.get_out(db, property_id, viewer_user_id, entry_id) -> LogEntryOut` (raises `NotFound`)
  - `app.domain.log.photo_url(property_id, entry_id) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_log_api.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k "feed or entry_out or mentioning"`
Expected: FAIL with `AttributeError: module 'app.domain.log' has no attribute 'feed'`

- [ ] **Step 3: Implement the read side**

Append to `server/app/domain/log.py`:

```python
def photo_url(property_id: str, entry_id: str) -> str:
    return f"/api/p/{property_id}/log-entries/{entry_id}/photo"


def _encode_cursor(entry: LogEntry) -> str:
    return f"{entry.created_at.isoformat()}|{entry.id}"


def _decode_cursor(raw: str) -> tuple[datetime, str]:
    created, _, entry_id = raw.partition("|")
    try:
        return datetime.fromisoformat(created), entry_id
    except ValueError as e:
        raise ValidationFailed("Invalid cursor") from e


def _viewer_department_ids(db: Session, property_id: str, user_id: str) -> list[str]:
    return list(db.scalars(select(PropertyMembership.department_id).where(
        PropertyMembership.property_id == property_id,
        PropertyMembership.user_id == user_id,
        PropertyMembership.department_id.is_not(None))).all())


def _to_out(db: Session, entries: list[LogEntry], viewer_user_id: str) -> list[LogEntryOut]:
    """One pass over a page of entries, batching the joins the cards need."""
    if not entries:
        return []
    ids = [e.id for e in entries]
    property_id = entries[0].property_id
    # Both lookups are property-scoped. An unscoped SELECT over user_account cannot leak
    # here (only ids present on this property's entries are read back), but it loads the
    # whole table on every feed page and is a standing trap in a property-isolated codebase.
    names: dict[str, str] = {}
    avatars: dict[str, str | None] = {}
    for uid, first, last, avatar in db.execute(
            select(UserAccount.id, UserAccount.first_name, UserAccount.last_name,
                   UserAccount.avatar_url)
            .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
            .where(PropertyMembership.property_id == property_id)).all():
        names[uid] = f"{first} {last}"
        avatars[uid] = avatar
    dept_names = dict(db.execute(
        select(Department.id, Department.name)
        .where(Department.property_id == property_id)).all())

    mentions: dict[str, list[LogMentionOut]] = {i: [] for i in ids}
    for row in db.scalars(select(LogEntryMention)
                          .where(LogEntryMention.log_entry_id.in_(ids))
                          .order_by(LogEntryMention.position)).all():
        display = (names.get(row.target_id) if row.type == MentionTargetType.user
                   else dept_names.get(row.target_id)) or "Unknown"
        mentions[row.log_entry_id].append(
            LogMentionOut(type=row.type, id=row.target_id, display_name=display))

    acks: dict[str, list[LogAckOut]] = {i: [] for i in ids}
    for row in db.scalars(select(LogEntryAck)
                          .where(LogEntryAck.log_entry_id.in_(ids))
                          .order_by(LogEntryAck.acknowledged_at)).all():
        acks[row.log_entry_id].append(
            LogAckOut(user_id=row.user_id, name=names.get(row.user_id, "Unknown"),
                      acknowledged_at=row.acknowledged_at))

    has_photo = set(db.scalars(select(LogEntryPhoto.log_entry_id)
                               .where(LogEntryPhoto.log_entry_id.in_(ids))).all())

    out: list[LogEntryOut] = []
    for e in entries:
        acked = {a.user_id for a in acks[e.id]}
        expected = list(e.ack_expected or [])
        out.append(LogEntryOut(
            id=e.id, created_at=e.created_at,
            author_user_id=e.author_user_id,
            author_name=names.get(e.author_user_id, "Unknown"),
            author_avatar_url=avatars.get(e.author_user_id),
            department_id=e.department_id,
            department_name=dept_names.get(e.department_id) if e.department_id else None,
            shift=e.shift, body=e.body, mentions=mentions[e.id],
            pinned=e.pinned, pinned_by_user_id=e.pinned_by_user_id, pinned_at=e.pinned_at,
            requires_ack=e.requires_ack, ack_expected_count=len(expected),
            acks=acks[e.id],
            outstanding=[LogPersonOut(user_id=u, name=names.get(u, "Unknown"))
                         for u in expected if u not in acked],
            acked_by_me=viewer_user_id in acked,
            can_ack=viewer_user_id in expected and viewer_user_id not in acked,
            photo_url=photo_url(e.property_id, e.id) if e.id in has_photo else None,
            linked_work_order_id=e.linked_work_order_id,
            linked_conversation_id=e.linked_conversation_id,
        ))
    return out


def feed(db: Session, property_id: str, viewer_user_id: str, query: LogFeedQuery) -> LogFeedOut:
    stmt = select(LogEntry).where(LogEntry.property_id == property_id)
    if query.shift:
        stmt = stmt.where(LogEntry.shift == query.shift)
    if query.department_id:
        stmt = stmt.where(LogEntry.department_id == query.department_id)
    if query.from_:
        stmt = stmt.where(LogEntry.created_at >= _day_bound(db, property_id, query.from_, False))
    if query.to:
        stmt = stmt.where(LogEntry.created_at < _day_bound(db, property_id, query.to, True))
    if query.mentioning_me:
        dept_ids = _viewer_department_ids(db, property_id, viewer_user_id)
        stmt = stmt.where(select(LogEntryMention.id).where(
            LogEntryMention.log_entry_id == LogEntry.id,
            or_(and_(LogEntryMention.type == MentionTargetType.user,
                     LogEntryMention.target_id == viewer_user_id),
                and_(LogEntryMention.type == MentionTargetType.department,
                     LogEntryMention.target_id.in_(dept_ids or [""])))).exists())
    if query.cursor:
        created, entry_id = _decode_cursor(query.cursor)
        stmt = stmt.where(tuple_(LogEntry.created_at, LogEntry.id) < (created, entry_id))

    rows = list(db.scalars(
        stmt.order_by(LogEntry.created_at.desc(), LogEntry.id.desc())
        .limit(FEED_PAGE_SIZE + 1)).all())
    next_cursor = _encode_cursor(rows[FEED_PAGE_SIZE - 1]) if len(rows) > FEED_PAGE_SIZE else None
    rows = rows[:FEED_PAGE_SIZE]

    pinned_rows = list(db.scalars(
        select(LogEntry)
        .where(LogEntry.property_id == property_id, LogEntry.pinned.is_(True))
        .order_by(LogEntry.created_at.desc())).all())

    return LogFeedOut(pinned=_to_out(db, pinned_rows, viewer_user_id),
                      entries=_to_out(db, rows, viewer_user_id),
                      next_cursor=next_cursor)


def get(db: Session, property_id: str, entry_id: str) -> LogEntry:
    entry = db.get(LogEntry, entry_id)
    if entry is None or entry.property_id != property_id:
        raise NotFound("Log entry not found")
    return entry


def get_out(db: Session, property_id: str, viewer_user_id: str, entry_id: str) -> LogEntryOut:
    return _to_out(db, [get(db, property_id, entry_id)], viewer_user_id)[0]
```

Add `_day_bound`, which turns an ISO date in the property timezone into a UTC instant:

```python
def _day_bound(db: Session, property_id: str, iso_date: str, exclusive_end: bool) -> datetime:
    """`from`/`to` are dates on the property's clock, not UTC (spec §4.2)."""
    prop = db.get(Property, property_id)
    try:
        day = date.fromisoformat(iso_date)
    except ValueError as e:
        raise ValidationFailed("Dates must be ISO (YYYY-MM-DD)") from e
    if exclusive_end:
        day = day + timedelta(days=1)
    tz = ZoneInfo(prop.timezone)
    return datetime.combine(day, time(0, 0), tzinfo=tz).astimezone(UTC)
```

Extend the module imports: `from datetime import UTC, date, datetime, time, timedelta`, `from sqlalchemy import and_, or_, select, tuple_`, `from app.errors import NotFound, ValidationFailed`, the new models `LogEntryAck`, and the schema names `FEED_PAGE_SIZE`, `LogAckOut`, `LogEntryOut`, `LogFeedOut`, `LogFeedQuery`, `LogMentionOut`, `LogPersonOut`.

- [ ] **Step 4: Run to verify they pass**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q`
Expected: PASS, 12 tests.

- [ ] **Step 5: Full suite, lint, commit**

```bash
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .
git add server/app/domain/log.py server/tests/test_log_api.py
git commit -m "feat(server): hotel log feed with filters, cursor and pinned block"
```

---

