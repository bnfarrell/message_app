## Task 3: Capabilities, both sides

**Files:**
- Modify: `server/app/auth/permissions.py:6`, `web/src/auth/capabilities.ts`
- Test: `server/tests/test_auth.py`, `web/src/auth/capabilities.test.ts`

**Interfaces:**
- Produces: capability strings `"view_log"`, `"post_log"`, `"pin_log_entry"` on the server; the same three added to the TypeScript `Capability` union

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_auth.py`:

```python
def test_log_capabilities_match_the_spec():
    from app.auth.permissions import has_capability
    from app.schemas.enums import Role

    for role in Role:
        assert has_capability(role, "view_log"), role
        assert has_capability(role, "post_log"), role
    assert not has_capability(Role.agent, "pin_log_entry")
    assert not has_capability(Role.dept_staff, "pin_log_entry")
    assert not has_capability(Role.corporate, "pin_log_entry")
    for role in (Role.supervisor, Role.manager, Role.admin):
        # admin must be able to pin: test_isolation.py asserts an admin is never 403 on a
        # route of their own property, and the pin routes carry @require_capability.
        assert has_capability(role, "pin_log_entry"), role
```

Append to `web/src/auth/capabilities.test.ts` (create the file if it does not exist, matching the import style of its neighbours):

```ts
import { describe, expect, it } from 'vitest'
import { hasCapability } from './capabilities'
import type { Role } from '../api/types'

describe('log capabilities', () => {
  const roles: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']

  it('lets every staff role read and post', () => {
    for (const role of roles) {
      expect(hasCapability(role, 'view_log')).toBe(true)
      expect(hasCapability(role, 'post_log')).toBe(true)
    }
  })

  it('restricts pinning to supervisor and above', () => {
    expect(hasCapability('agent', 'pin_log_entry')).toBe(false)
    expect(hasCapability('dept_staff', 'pin_log_entry')).toBe(false)
    expect(hasCapability('corporate', 'pin_log_entry')).toBe(false)
    expect(hasCapability('supervisor', 'pin_log_entry')).toBe(true)
    expect(hasCapability('manager', 'pin_log_entry')).toBe(true)
    expect(hasCapability('admin', 'pin_log_entry')).toBe(true)
  })
})
```

- [ ] **Step 2: Run both to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_auth.py -q -k log_capabilities`
Expected: FAIL — `has_capability` returns False for an unknown capability, so the first assert fails.

Run: `cd web && npm test -- capabilities`
Expected: FAIL — TypeScript rejects `'view_log'` as not assignable to `Capability`.

- [ ] **Step 3: Add the server capabilities**

In `server/app/auth/permissions.py`, inside `CAPABILITIES`, after `"export"`:

```python
    "view_log": STAFF,
    "post_log": STAFF,
    "pin_log_entry": {Role.supervisor, Role.manager, Role.admin},
```

- [ ] **Step 4: Mirror them in the web**

In `web/src/auth/capabilities.ts`, add to the `Capability` union and to the `CAPABILITIES` record:

```ts
  | 'view_log'
  | 'post_log'
  | 'pin_log_entry'
```

```ts
  view_log: STAFF,
  post_log: STAFF,
  pin_log_entry: ['supervisor', 'manager', 'admin'],
```

- [ ] **Step 5: Run both to verify they pass**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_auth.py -q`
Expected: PASS

Run: `cd web && npm test -- capabilities && npm run lint`
Expected: PASS, lint clean

- [ ] **Step 6: Commit**

```bash
git add server/app/auth/permissions.py server/tests/test_auth.py web/src/auth/capabilities.ts web/src/auth/capabilities.test.ts
git commit -m "feat: add view_log, post_log and pin_log_entry capabilities"
```

---

