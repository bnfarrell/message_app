# Task 3 Report: Capabilities, both sides

## What was implemented

Added three new hotel log capabilities to both server and web, following the TDD methodology:

1. **view_log**: Available to all STAFF roles (agent, dept_staff, supervisor, manager, admin, corporate) for reading the hotel log
2. **post_log**: Available to all STAFF roles for posting entries to the hotel log  
3. **pin_log_entry**: Available only to supervisor, manager, and admin roles for pinning important log entries

The implementation maintains the authorization table in both places:
- `server/app/auth/permissions.py` (authoritative)
- `web/src/auth/capabilities.ts` (mirror)

## TDD Evidence

### Step 1-2: Write and verify failing tests

**Server test (RED):**
```
Command: cd C:\Users\bryan\claude_code\relay\server && ..\.venv\Scripts\python.exe -m pytest tests/test_auth.py::test_log_capabilities_match_the_spec -q
Exit code: 1
Output: FAILED tests/test_auth.py::test_log_capabilities_match_the_spec - AssertionError: agent
```
Failure reason: `has_capability()` returns False for unknown capabilities. The assertion on line 122 (`assert has_capability(role, "view_log"), role`) failed because "view_log" was not yet in the CAPABILITIES dictionary.

**Web test (RED):**
```
Command: cd C:\Users\bryan\claude_code\relay\web && npm test -- capabilities
Exit code: 1
Output: FAIL src/auth/capabilities.test.ts > log capabilities > lets every staff role read and post
         FAIL src/auth/capabilities.test.ts > log capabilities > restricts pinning to supervisor and above
```
Failure reason: TypeScript compilation failed because 'view_log', 'post_log', and 'pin_log_entry' were not assignable to the `Capability` union type. The runtime also failed with "Cannot read properties of undefined" when accessing CAPABILITIES[capability] for these unknown capabilities.

### Step 3-4: Implement the capabilities

**Server:** Added to `server/app/auth/permissions.py`:
```python
"view_log": STAFF,
"post_log": STAFF,
"pin_log_entry": {Role.supervisor, Role.manager, Role.admin},
```

**Web:** Added to `web/src/auth/capabilities.ts`:
```ts
export type Capability =
  ...
  | 'view_log'
  | 'post_log'
  | 'pin_log_entry'

const CAPABILITIES: Record<Capability, Role[]> = {
  ...
  view_log: STAFF,
  post_log: STAFF,
  pin_log_entry: ['supervisor', 'manager', 'admin'],
}
```

### Step 5: Verify passing tests (GREEN)

**Server test (PASS):**
```
Command: cd C:\Users\byron\claude_code\relay\server && ..\.venv\Scripts\python.exe -m pytest tests/test_auth.py::test_log_capabilities_match_the_spec -q
Output: . [100%]
        1 passed in 0.04s
```

**Web test (PASS):**
```
Command: cd C:\Users\bryan\claude_code\relay\web && npm test -- capabilities
Output: Test Files  1 passed (1)
        Tests  9 passed (9)
```

### Full test suite results

**Backend:** 
- Before: 398 passed
- After: 399 passed
- Command: `cd server && ../.venv/Scripts/python.exe -m pytest -q`
- Result: All 399 tests passed in 44.57s

**Frontend:**
- Before: 599 passed across 59 files
- After: 601 passed across 59 files (9 in capabilities.test.ts: 7 existing + 2 new)
- Command: `cd web && npm test`
- Result: All 601 tests passed in 39.62s

### Linter results

**Backend (Python Ruff):**
```
Command: cd server && ../.venv/Scripts/python.exe -m ruff check .
Output: All checks passed!
```

**Frontend (ESLint):**
```
Command: cd web && npm run lint
Output: (no errors)
```

## Files Changed

1. **server/app/auth/permissions.py** (+3 lines)
   - Added three capabilities to the CAPABILITIES dictionary

2. **server/tests/test_auth.py** (+16 lines)
   - Added `test_log_capabilities_match_the_spec()` function with assertions for all role-capability combinations

3. **web/src/auth/capabilities.ts** (+6 lines)
   - Added three types to the Capability union
   - Added three entries to the CAPABILITIES record

4. **web/src/auth/capabilities.test.ts** (+20 lines)
   - Added "log capabilities" describe block with two test cases:
     - "lets every staff role read and post" 
     - "restricts pinning to supervisor and above"

## Commit

```
Commit: 9aa21bc
Subject: feat: add view_log, post_log and pin_log_entry capabilities
```

## Self-review findings

### What went well
- TDD workflow followed perfectly: tests written first, verified failing, implementation added, verified passing
- Both authorization tables kept in strict synchronization
- Tests are comprehensive and validate all role-capability combinations
- No existing tests were broken
- Code follows the existing patterns and style in both files
- Proper attribution added to commit message

### Design notes
- `pin_log_entry` correctly includes `Role.admin` to satisfy test_isolation.py constraint that admin users are never 403 on their own property routes
- `view_log` and `post_log` use the existing `STAFF` constant for brevity and maintainability
- All three capabilities implemented as specified in the brief

### Concerns
None. The implementation is complete, tested, and verified. No blocking issues or concerns.

---

**Report created:** 2026-09-19
**Task status:** Complete
