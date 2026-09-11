### Task 6: Server — expose and persist user preferences (ruling R1)

**Files:**
- Modify: `server/app/schemas/auth.py` (add `notification_prefs` to `UserOut`; add `PrefsPatch`)
- Modify: `server/app/api/auth.py` (add `PATCH /api/auth/prefs`)
- Modify: `web/src/api/schema.json` (regenerated), `web/src/api/types.generated.ts` (regenerated)
- Test: `server/tests/test_auth_prefs.py`

**Interfaces:**
- Consumes: nothing from the web tasks.
- Produces: `UserOut.notificationPrefs: Record<string, unknown>` on every `/api/auth/login` and `/api/auth/me` response, and `PATCH /api/auth/prefs {theme?: 'dark' | 'light' | 'system'}` → the updated `SessionOut`. Task 8 consumes both.

**Why this task exists:** §5.0 says the theme is "persisted in `notification_prefs.theme`". The column exists (`server/app/models/core.py:61`) but nothing reads or writes it and `UserOut` does not expose it — see ruling **R1**. This is the smallest change that makes the spec's sentence true. It is a server diff inside a web plan; keep it to these files.

**Deliberately narrow:** the endpoint accepts *only* `theme`. A general "merge any JSON into `notification_prefs`" endpoint would let a client write unbounded keys into a column nothing validates. Phase 2 can widen it when there are real notification preferences to set.

- [ ] **Step 1: Write the failing test**

`server/tests/test_auth_prefs.py`:

```python
from tests.fixtures import PASSWORD


def test_me_exposes_notification_prefs(client, fx, login):
    c = login(fx.agent_a.email)
    body = c.get("/api/auth/me").get_json()
    assert body["user"]["notificationPrefs"] == {}


def test_login_exposes_notification_prefs(client, fx):
    res = client.post("/api/auth/login",
                      json={"email": fx.agent_a.email, "password": PASSWORD})
    assert res.status_code == 200
    assert res.get_json()["user"]["notificationPrefs"] == {}


def test_patch_prefs_persists_the_theme_and_returns_the_session(fx, login):
    c = login(fx.agent_a.email)
    res = c.patch("/api/auth/prefs", json={"theme": "light"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["user"]["notificationPrefs"]["theme"] == "light"
    # A fresh request sees it: this is the whole point — the theme follows the user.
    assert c.get("/api/auth/me").get_json()["user"]["notificationPrefs"]["theme"] == "light"


def test_patch_prefs_survives_a_new_session(fx, login):
    """The value must be on the row, not in the session — this is the whole point of R1."""
    login(fx.agent_a.email).patch("/api/auth/prefs", json={"theme": "light"})
    fresh = login(fx.agent_a.email)
    assert fresh.get("/api/auth/me").get_json()["user"]["notificationPrefs"]["theme"] == "light"


def test_patch_prefs_merges_rather_than_replacing(fx, login):
    c = login(fx.agent_a.email)
    c.patch("/api/auth/prefs", json={"theme": "light"})
    c.patch("/api/auth/prefs", json={"theme": "dark"})
    prefs = c.get("/api/auth/me").get_json()["user"]["notificationPrefs"]
    assert prefs["theme"] == "dark"


def test_patch_prefs_rejects_an_unknown_theme(fx, login):
    c = login(fx.agent_a.email)
    res = c.patch("/api/auth/prefs", json={"theme": "sepia"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_patch_prefs_rejects_unknown_keys(fx, login):
    c = login(fx.agent_a.email)
    res = c.patch("/api/auth/prefs", json={"theme": "light", "isAdmin": True})
    assert res.status_code == 400


def test_patch_prefs_requires_a_session(client):
    res = client.patch("/api/auth/prefs", json={"theme": "light"})
    assert res.status_code == 401


def test_patch_prefs_only_touches_the_caller(fx, login):
    login(fx.agent_a.email).patch("/api/auth/prefs", json={"theme": "light"})
    other = login(fx.agent_a2.email)
    assert other.get("/api/auth/me").get_json()["user"]["notificationPrefs"] == {}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd server && python -m pytest tests/test_auth_prefs.py -v
```

Expected: FAIL — `KeyError: 'notificationPrefs'` on the first tests and 405 on the `PATCH` ones.

- [ ] **Step 3: Add the schema fields**

In `server/app/schemas/auth.py`, add the import and the two changes. `UserOut` inherits `CamelModel`, so `notification_prefs` serialises as `notificationPrefs` automatically.

```python
from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.common import CamelModel
from app.schemas.enums import Role


class UserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    locale: str
    notification_prefs: dict = Field(default_factory=dict)


class PrefsPatch(CamelModel):
    """Only the keys the client is allowed to set. `extra='forbid'` comes from CamelModel."""

    theme: Literal["dark", "light", "system"] | None = None
```

- [ ] **Step 4: Add the endpoint**

In `server/app/api/auth.py`, extend the imports (`PrefsPatch`, `parse_body`) and append:

```python
@bp.patch("/prefs")
@require_auth
def patch_prefs():
    body = parse_body(PrefsPatch)
    with db_session() as db:
        user = db.get(UserAccount, g.user.id)
        # Reassign rather than mutate: a JSON column mutated in place is not seen as dirty
        # by SQLAlchemy without MutableDict, so the UPDATE would never be emitted.
        prefs = dict(user.notification_prefs or {})
        if body.theme is not None:
            prefs["theme"] = body.theme
        user.notification_prefs = prefs
        return ok(_session_out(db, user))
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd server && python -m pytest tests/test_auth_prefs.py -v
```

Expected: PASS — 9 tests. The in-place-mutation comment in Step 4 is the failure mode to watch: if `test_patch_prefs_persists_the_theme_and_returns_the_session` passes but `test_patch_prefs_survives_a_new_session` fails, the reassignment was dropped.

- [ ] **Step 6: Run the whole server suite, then regenerate the schema and types**

```bash
cd server && python -m pytest -q
```

Expected: every test green **except** `tests/test_schema_export.py::test_committed_schema_is_current`, which compares `web/src/api/schema.json` against a fresh `build()`. `UserOut` just changed, so it fails — that failure is the guard working, not a defect. Regenerate:

```bash
cd .. && npm run schema && cd web && npm run gen:types && cd ../server && python -m pytest -q && cd ../web && npm test
```

Expected: both suites green; `git status` shows `web/src/api/schema.json` and `web/src/api/types.generated.ts` modified.

- [ ] **Step 7: Commit**

```bash
git add server/app/schemas/auth.py server/app/api/auth.py server/tests/test_auth_prefs.py \
        web/src/api/schema.json web/src/api/types.generated.ts
git commit -m "feat(server): expose notification prefs and let a user persist their theme"
```

---

