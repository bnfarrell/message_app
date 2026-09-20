## Task 7: Acknowledge and pin

**Files:**
- Modify: `server/app/domain/log.py`
- Test: `server/tests/test_log_api.py`

**Interfaces:**
- Produces:
  - `app.domain.log.acknowledge(db, property_id, user_id, entry_id) -> LogEntry` (raises `Forbidden` when the user is not expected)
  - `app.domain.log.set_pinned(db, property_id, user_id, entry_id, pinned: bool) -> LogEntry`

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_log_api.py`:

```python
def test_acknowledging_twice_is_idempotent(database, fx):
    from app.models import LogEntryAck

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
        log_domain.set_pinned(db, fx.property_a.id, fx.supervisor_a.id, entry.id, False)
        db.flush()
        page2 = log_domain.feed(db, fx.property_a.id, fx.agent_a.id, LogFeedQuery())
        assert page2.pinned == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k "acknowledg or pin or denominator"`
Expected: FAIL with `AttributeError: module 'app.domain.log' has no attribute 'acknowledge'`

- [ ] **Step 3: Implement**

Append to `server/app/domain/log.py`:

```python
def acknowledge(db: Session, property_id: str, user_id: str, entry_id: str) -> LogEntry:
    entry = get(db, property_id, entry_id)
    if user_id not in (entry.ack_expected or []):
        # An acknowledgement from somebody who was never asked is noise in the audit
        # trail, so it is refused rather than silently recorded (spec §5).
        raise Forbidden("You were not asked to acknowledge this entry")
    existing = db.scalar(select(LogEntryAck).where(
        LogEntryAck.log_entry_id == entry.id, LogEntryAck.user_id == user_id))
    if existing is not None:
        return entry
    db.add(LogEntryAck(log_entry_id=entry.id, property_id=property_id, user_id=user_id,
                       acknowledged_at=clock.now()))
    db.flush()
    audit.record(db, property_id, user_id, "log_entry.acknowledged", "log_entry", entry.id)
    queue_event(db, property_id, "log.entry.updated", {"id": entry.id})
    return entry


def set_pinned(db: Session, property_id: str, user_id: str, entry_id: str,
               pinned: bool) -> LogEntry:
    entry = get(db, property_id, entry_id)
    if entry.pinned == pinned:
        return entry
    before = {"pinned": entry.pinned}
    entry.pinned = pinned
    entry.pinned_by_user_id = user_id if pinned else None
    entry.pinned_at = clock.now() if pinned else None
    db.flush()
    audit.record(db, property_id, user_id, "log_entry.pinned" if pinned else
                 "log_entry.unpinned", "log_entry", entry.id,
                 before=before, after={"pinned": pinned})
    queue_event(db, property_id, "log.entry.updated", {"id": entry.id})
    return entry
```

Add `Forbidden` to the `app.errors` import and `LogEntryAck` to the models import.

- [ ] **Step 4: Run to verify they pass**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q`
Expected: PASS, 16 tests.

- [ ] **Step 5: Full suite, lint, commit**

```bash
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .
git add server/app/domain/log.py server/tests/test_log_api.py
git commit -m "feat(server): acknowledge and pin hotel log entries"
```

---

