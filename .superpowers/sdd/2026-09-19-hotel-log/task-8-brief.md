## Task 8: The API blueprint

**Files:**
- Create: `server/app/api/log.py`
- Modify: `server/app/__init__.py`
- Test: `server/tests/test_log_api.py`

**Interfaces:**
- Consumes: everything from Tasks 4–7; `MAX_PHOTO_BYTES` and `sniff_image_type` from `app.domain.work_orders`
- Produces: the eight routes of spec §4.1, and `app.api.log.bp`

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_log_api.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k "api or pin or photo or mentionables or immutab or body"`
Expected: FAIL with 404s — the blueprint is not registered.

- [ ] **Step 3: Write the blueprint**

Create `server/app/api/log.py`:

```python
from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import log
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import ValidationFailed
from app.schemas.log import CreateLogEntryRequest, LogFeedQuery

bp = Blueprint("log", __name__, url_prefix="/api/p/<property_id>/log-entries")


def _photo_from_request() -> tuple[bytes, str] | None:
    upload = request.files.get("photo")
    if upload is None:
        return None
    body = upload.read(MAX_PHOTO_BYTES + 1)
    if len(body) > MAX_PHOTO_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    content_type = sniff_image_type(body)
    if content_type is None:
        raise ValidationFailed("A photo must be a JPEG, PNG or WebP image",
                               details={"photo": "unsupported_image_type"})
    return body, content_type


@bp.get("")
@require_auth
@require_property
@require_capability("view_log")
def list_entries(property_id: str):
    query = parse_query(LogFeedQuery)
    with db_session() as db:
        return ok(log.feed(db, g.property_id, g.user.id, query))


@bp.post("")
@require_auth
@require_property
@require_capability("post_log")
def create_entry(property_id: str):
    data = parse_body(CreateLogEntryRequest)
    photo = _photo_from_request()
    with db_session() as db:
        entry = log.create(db, g.property_id, g.user.id, data, photo=photo)
        return ok(log.get_out(db, g.property_id, g.user.id, entry.id), 201)


@bp.get("/mentionables")
@require_auth
@require_property
@require_capability("view_log")
def mentionables(property_id: str):
    with db_session() as db:
        return ok(log.mentionables(db, g.property_id))


@bp.get("/<entry_id>")
@require_auth
@require_property
@require_capability("view_log")
def get_entry(property_id: str, entry_id: str):
    with db_session() as db:
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.post("/<entry_id>/ack")
@require_auth
@require_property
@require_capability("view_log")
def ack_entry(property_id: str, entry_id: str):
    with db_session() as db:
        log.acknowledge(db, g.property_id, g.user.id, entry_id)
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.post("/<entry_id>/pin")
@require_auth
@require_property
@require_capability("pin_log_entry")
def pin_entry(property_id: str, entry_id: str):
    with db_session() as db:
        log.set_pinned(db, g.property_id, g.user.id, entry_id, True)
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.delete("/<entry_id>/pin")
@require_auth
@require_property
@require_capability("pin_log_entry")
def unpin_entry(property_id: str, entry_id: str):
    with db_session() as db:
        log.set_pinned(db, g.property_id, g.user.id, entry_id, False)
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.get("/<entry_id>/photo")
@require_auth
@require_property
@require_capability("view_log")
def get_entry_photo(property_id: str, entry_id: str):
    with db_session() as db:
        body, content_type = log.get_photo(db, g.property_id, entry_id)
    return Response(body, mimetype=content_type,
                    headers={"Cache-Control": "private, max-age=86400"})
```

**Route-order note:** `/mentionables` is declared before `/<entry_id>` deliberately. Flask matches static rules ahead of converters regardless of declaration order, but keeping them in this order makes the intent obvious to the next reader.

- [ ] **Step 4: Add the two domain functions the blueprint needs**

Append to `server/app/domain/log.py`:

```python
def mentionables(db: Session, property_id: str) -> list[LogMentionableOut]:
    """One flat list for the composer's picker: every active member, then every
    department. Ids are what the composer records; display names are presentation only."""
    rows = db.execute(
        select(UserAccount.id, UserAccount.first_name, UserAccount.last_name,
               PropertyMembership.role)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .where(PropertyMembership.property_id == property_id,
               UserAccount.status == UserStatus.active)
        .order_by(UserAccount.first_name, UserAccount.last_name)).all()
    people = [LogMentionableOut(type=MentionTargetType.user, id=uid,
                                display_name=f"{first} {last}", subtitle=role.value)
              for uid, first, last, role in rows]
    dept_rows = db.execute(
        select(Department.id, Department.name)
        .where(Department.property_id == property_id)
        .order_by(Department.name)).all()
    departments = [LogMentionableOut(type=MentionTargetType.department, id=did,
                                     display_name=name, subtitle="Department")
                   for did, name in dept_rows]
    return people + departments


def get_photo(db: Session, property_id: str, entry_id: str) -> tuple[bytes, str]:
    get(db, property_id, entry_id)  # 404s before the blob lookup, and scopes the property
    row = db.scalar(select(LogEntryPhoto)
                    .where(LogEntryPhoto.log_entry_id == entry_id,
                           LogEntryPhoto.property_id == property_id))
    if row is None:
        raise NotFound("No photo on this log entry")
    return row.data, row.content_type
```

Add `LogMentionableOut` to the schema imports.

- [ ] **Step 5: Register the blueprint**

In `server/app/__init__.py`, alongside the other registrations (after line 80):

```python
    app.register_blueprint(log.bp)
```

and add `log` to the `from app.api import (...)` import list at the top of that file.

- [ ] **Step 6: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py tests/test_isolation.py -q`
Expected: PASS. If `test_admin_of_a_is_not_403_on_own_property` fails, a capability excludes admin — fix the capability, not the test.

- [ ] **Step 7: Full suite, lint, commit**

```bash
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .
git add server/app/api/log.py server/app/__init__.py server/app/domain/log.py server/tests/test_log_api.py
git commit -m "feat(server): hotel log API routes"
```

---

