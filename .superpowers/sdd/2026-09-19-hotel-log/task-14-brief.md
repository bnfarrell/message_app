## Task 14: Seed data and full-stack verification

**Files:**
- Modify: `server/seed/` (read the directory first and follow its existing shape)
- Test: `server/tests/test_seed.py`

- [ ] **Step 1: Add seed entries**

Add three log entries to the dev seed for property A, chosen to exercise the feature rather than to look pretty:

1. An `am` shift-handover post from the front desk agent, tagging Front Desk, mentioning Housekeeping as a department, with a body modelled on the reference AM CHECKLIST in `images/image (2).png`.
2. A pinned `pm` post from the supervisor.
3. An `overnight` post requiring acknowledgement from Housekeeping, with nobody having acknowledged yet, so the UI shows a real outstanding list on first load.

- [ ] **Step 2: Extend `SeedSummary` and the seed test**

`SeedSummary` (`server/seed/seed.py:67`) is a dataclass of counts, and `test_seed.py` asserts **every** field against a real row count — its own comment says "SeedSummary must match real rows, not an in-memory counter that a rewire can desync". Follow that convention rather than only counting rows:

1. Add `log_entries: int` to the `SeedSummary` dataclass.
2. Populate it in `run()` from an actual query, not from a local tally.
3. In `test_seed.py`, add to the summary-vs-reality block:

```python
        assert summary.log_entries == count(LogEntry)
```

4. And, alongside the existing per-property count assertions, pin down what the seed actually produces:

```python
        assert count(LogEntry, LogEntry.property_id == hvh.id) == 3
        assert count(LogEntry, LogEntry.property_id == hvh.id, LogEntry.pinned.is_(True)) == 1
        assert count(LogEntry, LogEntry.property_id == hvh.id,
                     LogEntry.requires_ack.is_(True)) == 1
```

The exact-count style matches the surrounding assertions (`== 12`, `== 85`), which exist so a seed change is a deliberate test edit rather than a silent drift.

- [ ] **Step 3: Run the backend suite**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .`
Expected: all green, lint clean.

- [ ] **Step 4: Run the frontend suite**

Run: `cd web && npm test && npm run lint && npm run build`
Expected: all green, clean.

- [ ] **Step 5: Manual browser verification**

Start the app the way `start.bat` does, log in, and verify each acceptance criterion from spec §10 against the running application:

1. Post a note tagging Housekeeping, mentioning two people and one department, with a photo. Check the notification bell for the mentioned users; check the author receives nothing.
2. With two browser sessions open on the log, confirm a post from one appears in the other with no refresh.
3. As a supervisor, post requiring acknowledgement from Housekeeping; confirm the count reads `0 of N` with N the active housekeeping members minus the author, and that acknowledging as one of them moves it to `1 of N` and removes that name from outstanding.
4. Move a user into Housekeeping and confirm the existing entry's denominator does not change.
5. As an agent, confirm no Pin control appears; as a supervisor, pin and confirm the pinned block.
6. Confirm the shift badge on a seeded overnight entry reads overnight.
7. Confirm no UI affordance edits a posted body.
8. Confirm a direct URL to another property's log 403s.

Record the result of each check — pass or fail with what was observed — in the progress ledger.

- [ ] **Step 6: Commit**

```bash
git add server/seed server/tests/test_seed.py
git commit -m "feat(server): seed hotel log entries for development"
```

---

## Self-Review Notes

Checked against the spec, section by section:

- §3 data model → Task 1 (all four tables, both enums, the migration).
- §3.1 mentions table → Task 1 (schema) and Task 5 (writing rows in order).
- §3.2 ack snapshot, active-only, empty-audience downgrade → Task 5, with the "joins later" case verified again in Task 7.
- §3.3 shift derivation → Task 2.
- §4.1 all eight routes → Task 8.
- §4.2 feed, pinned block, four filters, cursor → Task 6.
- §4.3 create validation, cross-property rejection, photo → Tasks 5 and 8.
- §4.4 immutability → asserted on the route map in Task 8.
- §5 capabilities → Task 3, both sides.
- §6 mention fan-out and both notification types → Task 5.
- §6.1 token grammar and safe rendering → Tasks 10 and 12.
- §7 all five components, route, nav → Tasks 10–13.
- §8 two events, two switch cases → Tasks 5, 7 (emit) and 9 (consume).
- §9 test list → distributed across the tasks that own each behaviour.
- §10 acceptance criteria → Task 14 step 5, one check each.

Two things the spec implies that the plan makes explicit because an implementer would otherwise trip on them: `members_of_department` does not filter by status, so Task 5 adds `active_members_of_department` rather than silently changing shared behaviour; and multipart form posts deliver `mentions`/`ackAudience` as JSON strings, so Task 9 adds a `model_validator` for that path.
