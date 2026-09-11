### Task 16: Quick replies, digital assets, resolution categories — CRUD, search, short links

**Files:**
- Create: `server/app/schemas/content.py`, `server/app/domain/assets.py`, `server/app/domain/categories.py`, `server/app/api/quick_replies.py`, `server/app/api/assets.py`, `server/app/api/categories.py`, `server/app/api/short_links.py`, `server/tests/test_content.py`
- Modify: `server/app/domain/quick_replies.py` (add CRUD + search + `context_for_conversation`), `server/app/__init__.py`

**Interfaces:**
- Produces: `quick_replies.list(db, property_id, q=None, department_id=None, include_inactive=False) -> list[QuickReplyOut]`; `create/update/delete`; `quick_replies.render(db, property_id, quick_reply_id, conversation_id, agent_user_id) -> RenderedQuickReply` (interpolated body + segment count; bumps `usage_count`); `quick_replies.context_for_conversation(db, property_id, conversation_id, agent_user_id) -> dict`; `assets.list/create/update/delete/get_by_short_code`, `assets.new_short_code(db) -> str` (6 chars, base32, unique); `categories.list_tree/create/update/delete`. Schemas: `QuickReplyIn/Out`, `RenderedQuickReply`, `AssetIn/Out`, `CategoryIn/Out`. Routes: `quick-replies` (`GET ?q=&dept=&includeInactive=`, `POST`, `PATCH /<id>`, `DELETE /<id>`, `POST /<id>/render {conversationId}`), `assets` (`GET/POST/PATCH/DELETE`), `resolution-categories` (`GET/POST/PATCH/DELETE`), public `GET /a/<short_code>` → 302.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_content.py`:
```python
from sqlalchemy import select

from app.models import Conversation, DigitalAsset
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def test_quick_reply_crud_search_and_render(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/quick-replies"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"shortcut": "/wifi", "title": "WiFi", "body": "Hi {{guest_first_name}}, WiFi is Harbourview-Guest, room {{room_number}}."})
    assert r.status_code == 201
    qr = r.get_json()
    admin.post(base, json={"shortcut": "/towels", "title": "Towels", "body": "Towels on the way to {{room_number}}.",
                           "departmentId": fx.dept_housekeeping.id})
    dup = admin.post(base, json={"shortcut": "/wifi", "title": "x", "body": "y"})
    assert dup.status_code == 409
    agent = login("agent@hvh.test")
    assert [x["shortcut"] for x in agent.get(base + "?q=wif").get_json()] == ["/wifi"]
    assert [x["shortcut"] for x in agent.get(base + "?q=on the way").get_json()] == ["/towels"]
    assert agent.post(base, json={"shortcut": "/x", "title": "x", "body": "y"}).status_code == 403
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    rendered = agent.post(f"{base}/{qr['id']}/render", json={"conversationId": cid}).get_json()
    assert rendered["body"] == "Hi Sarah, WiFi is Harbourview-Guest, room 412."
    assert rendered["segments"] == 1
    assert agent.get(base).get_json()[0]["usageCount"] == 1  # sorted by usage desc
    assert admin.patch(f"{base}/{qr['id']}", json={"active": False}).status_code == 200
    assert [x["shortcut"] for x in agent.get(base).get_json()] == ["/towels"]
    assert len(admin.get(base + "?includeInactive=true").get_json()) == 2
    assert admin.delete(f"{base}/{qr['id']}").status_code == 204


def test_assets_crud_short_link_and_send_appends_link(app, fx, client, database, login, worker):
    base = f"/api/p/{fx.property_a.id}/assets"
    admin = login("admin@hvh.test")
    a = admin.post(base, json={"name": "WiFi card", "type": "link", "url": "https://example.test/wifi.pdf",
                               "category": "Connectivity"}).get_json()
    assert len(a["shortCode"]) == 6
    r = client.get(f"/a/{a['shortCode']}")
    assert r.status_code == 302 and r.headers["Location"] == "https://example.test/wifi.pdf"
    assert client.get("/a/nope00").status_code == 404
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "wifi?")
    cid = _cid(database, fx.guest_inhouse_a.id)
    agent = login("agent@hvh.test")
    m = agent.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                   json={"body": "Here you go:", "digitalAssetId": a["id"]}).get_json()
    assert m["body"] == f"Here you go: /a/{a['shortCode']}" and m["digitalAssetId"] == a["id"]
    with database.session() as db:
        assert db.get(DigitalAsset, a["id"]).send_count == 1
    assert admin.patch(f"{base}/{a['id']}", json={"name": "WiFi card v2"}).get_json()["name"] == "WiFi card v2"
    assert admin.delete(f"{base}/{a['id']}").status_code == 204
    assert client.get(f"/a/{a['shortCode']}").status_code == 404


def test_resolution_categories_tree(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/resolution-categories"
    admin = login("admin@hvh.test")
    parent = admin.post(base, json={"name": "Maintenance"}).get_json()
    child = admin.post(base, json={"name": "HVAC", "parentId": parent["id"]}).get_json()
    tree = admin.get(base).get_json()
    assert tree[0]["name"] == "Maintenance" and tree[0]["children"][0]["id"] == child["id"]
    assert admin.patch(f"{base}/{child['id']}", json={"name": "HVAC / AC"}).get_json()["name"] == "HVAC / AC"
    assert admin.delete(f"{base}/{parent['id']}").status_code == 409  # has children
    assert admin.delete(f"{base}/{child['id']}").status_code == 204
    assert admin.delete(f"{base}/{parent['id']}").status_code == 204
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_content.py -q`
Expected: FAIL with 404s.

- [ ] **Step 3: Write `app/schemas/content.py`**

```python
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import AssetType


class QuickReplyIn(CamelModel):
    shortcut: str = Field(min_length=2, max_length=40, pattern=r"^/[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1600)
    category: str | None = None
    department_id: str | None = None
    locale: str = "en"
    active: bool = True


class QuickReplyPatch(CamelModel):
    shortcut: str | None = Field(default=None, pattern=r"^/[a-z0-9_-]+$")
    title: str | None = None
    body: str | None = None
    category: str | None = None
    department_id: str | None = None
    active: bool | None = None


class QuickReplyOut(CamelModel):
    id: str
    shortcut: str
    title: str
    body: str
    category: str | None = None
    department_id: str | None = None
    locale: str
    usage_count: int
    active: bool


class RenderRequest(CamelModel):
    conversation_id: str


class RenderedQuickReply(CamelModel):
    body: str
    segments: int
    characters: int


class AssetIn(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    category: str | None = None
    type: AssetType = AssetType.link
    url: str = Field(min_length=1, max_length=1000)
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool = True
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class AssetPatch(CamelModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    type: AssetType | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class AssetOut(CamelModel):
    id: str
    name: str
    description: str | None = None
    category: str | None = None
    type: AssetType
    url: str
    short_code: str
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    send_count: int


class CategoryIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: str | None = None
    active: bool = True


class CategoryPatch(CamelModel):
    name: str | None = None
    parent_id: str | None = None
    active: bool | None = None


class CategoryOut(CamelModel):
    id: str
    name: str
    parent_id: str | None = None
    active: bool
    children: list["CategoryOut"] = []
```

- [ ] **Step 4: Extend `app/domain/quick_replies.py`**

Append (imports: `select, or_, func` from sqlalchemy; `Session`; `Conversation, Guest, Property, QuickReply, Stay, UserAccount`; `Conflict, NotFound`; schemas; `segment_count` from `app.domain.sms`; `conv_domain`):
```python
def list(db: Session, property_id: str, q: str | None = None, department_id: str | None = None,
         include_inactive: bool = False) -> list[QuickReplyOut]:
    stmt = select(QuickReply).where(QuickReply.property_id == property_id)
    if not include_inactive:
        stmt = stmt.where(QuickReply.active.is_(True))
    if department_id:
        stmt = stmt.where(or_(QuickReply.department_id == department_id, QuickReply.department_id.is_(None)))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(QuickReply.shortcut).like(like), func.lower(QuickReply.title).like(like),
                              func.lower(QuickReply.body).like(like)))
    rows = db.scalars(stmt.order_by(QuickReply.usage_count.desc(), QuickReply.shortcut)).all()
    return [QuickReplyOut.model_validate(r) for r in rows]


def get(db: Session, property_id: str, quick_reply_id: str) -> QuickReply:
    r = db.scalar(select(QuickReply).where(QuickReply.id == quick_reply_id, QuickReply.property_id == property_id))
    if r is None:
        raise NotFound("Quick reply not found")
    return r


def _assert_shortcut_free(db: Session, property_id: str, shortcut: str, exclude_id: str | None = None) -> None:
    stmt = select(QuickReply.id).where(QuickReply.property_id == property_id, QuickReply.shortcut == shortcut)
    if exclude_id:
        stmt = stmt.where(QuickReply.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"Shortcut {shortcut} is already in use")


def create(db: Session, property_id: str, data: QuickReplyIn) -> QuickReply:
    _assert_shortcut_free(db, property_id, data.shortcut)
    r = QuickReply(property_id=property_id, **data.model_dump())
    db.add(r)
    db.flush()
    return r


def update(db: Session, property_id: str, quick_reply_id: str, data: QuickReplyPatch) -> QuickReply:
    r = get(db, property_id, quick_reply_id)
    changes = data.model_dump(exclude_unset=True)
    if "shortcut" in changes and changes["shortcut"]:
        _assert_shortcut_free(db, property_id, changes["shortcut"], exclude_id=r.id)
    for k, v in changes.items():
        setattr(r, k, v)
    db.flush()
    return r


def delete(db: Session, property_id: str, quick_reply_id: str) -> None:
    db.delete(get(db, property_id, quick_reply_id))


def context_for_conversation(db: Session, property_id: str, conversation_id: str, agent_user_id: str | None) -> dict:
    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    stay = db.get(Stay, conv.stay_id) if conv.stay_id else None
    prop = db.get(Property, property_id)
    agent = db.get(UserAccount, agent_user_id) if agent_user_id else None
    return {
        "guest_first_name": guest.first_name,
        "room_number": stay.room_number if stay else None,
        "property_name": prop.name,
        "agent_first_name": agent.first_name if agent else None,
        "departure_date": stay.departure_date.strftime("%A, %b %d") if stay else None,
    }


def render(db: Session, property_id: str, quick_reply_id: str, conversation_id: str,
           agent_user_id: str | None) -> RenderedQuickReply:
    r = get(db, property_id, quick_reply_id)
    body = interpolate(r.body, context_for_conversation(db, property_id, conversation_id, agent_user_id))
    r.usage_count += 1
    return RenderedQuickReply(body=body, segments=segment_count(body), characters=len(body))
```

- [ ] **Step 5: Write `app/domain/assets.py` and `app/domain/categories.py`**

`assets.py`:
```python
from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import DigitalAsset
from app.schemas.content import AssetIn, AssetOut, AssetPatch

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o/1/l/i


def new_short_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not db.scalar(select(DigitalAsset.id).where(DigitalAsset.short_code == code)):
            return code


def list(db: Session, property_id: str, include_inactive: bool = False) -> list[AssetOut]:
    stmt = select(DigitalAsset).where(DigitalAsset.property_id == property_id)
    if not include_inactive:
        stmt = stmt.where(DigitalAsset.active.is_(True))
    return [AssetOut.model_validate(a) for a in db.scalars(stmt.order_by(DigitalAsset.name)).all()]


def get(db: Session, property_id: str, asset_id: str) -> DigitalAsset:
    a = db.scalar(select(DigitalAsset).where(DigitalAsset.id == asset_id, DigitalAsset.property_id == property_id))
    if a is None:
        raise NotFound("Asset not found")
    return a


def get_by_short_code(db: Session, short_code: str) -> DigitalAsset | None:
    return db.scalar(select(DigitalAsset).where(DigitalAsset.short_code == short_code, DigitalAsset.active.is_(True)))


def create(db: Session, property_id: str, data: AssetIn) -> DigitalAsset:
    a = DigitalAsset(property_id=property_id, short_code=new_short_code(db), **data.model_dump())
    db.add(a)
    db.flush()
    return a


def update(db: Session, property_id: str, asset_id: str, data: AssetPatch) -> DigitalAsset:
    a = get(db, property_id, asset_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.flush()
    return a


def delete(db: Session, property_id: str, asset_id: str) -> None:
    a = get(db, property_id, asset_id)
    a.active = False  # soft: messages already sent still reference the id; the short link stops resolving
```

`categories.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound
from app.models import ResolutionCategory
from app.schemas.content import CategoryIn, CategoryOut, CategoryPatch


def list_tree(db: Session, property_id: str) -> list[CategoryOut]:
    rows = db.scalars(select(ResolutionCategory).where(ResolutionCategory.property_id == property_id)
                      .order_by(ResolutionCategory.name)).all()
    nodes = {r.id: CategoryOut(id=r.id, name=r.name, parent_id=r.parent_id, active=r.active, children=[]) for r in rows}
    roots: list[CategoryOut] = []
    for r in rows:
        (nodes[r.parent_id].children if r.parent_id in nodes else roots).append(nodes[r.id])
    return roots


def get(db: Session, property_id: str, category_id: str) -> ResolutionCategory:
    c = db.scalar(select(ResolutionCategory).where(ResolutionCategory.id == category_id,
                                                   ResolutionCategory.property_id == property_id))
    if c is None:
        raise NotFound("Category not found")
    return c


def create(db: Session, property_id: str, data: CategoryIn) -> ResolutionCategory:
    if data.parent_id:
        get(db, property_id, data.parent_id)
    c = ResolutionCategory(property_id=property_id, **data.model_dump())
    db.add(c)
    db.flush()
    return c


def update(db: Session, property_id: str, category_id: str, data: CategoryPatch) -> ResolutionCategory:
    c = get(db, property_id, category_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.flush()
    return c


def delete(db: Session, property_id: str, category_id: str) -> None:
    c = get(db, property_id, category_id)
    if db.scalar(select(ResolutionCategory.id).where(ResolutionCategory.parent_id == c.id)):
        raise Conflict("Delete or move the child categories first")
    db.delete(c)
```

- [ ] **Step 6: Write the four blueprints and register them**

`app/api/quick_replies.py`:
```python
from flask import Blueprint, g, request

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import quick_replies
from app.schemas.content import QuickReplyIn, QuickReplyOut, QuickReplyPatch, RenderRequest

bp = Blueprint("quick_replies", __name__, url_prefix="/api/p/<property_id>/quick-replies")


@bp.get("")
@require_auth
@require_property
def list_quick_replies(property_id: str):
    with db_session() as db:
        return ok(quick_replies.list(db, g.property_id, q=request.args.get("q"), department_id=request.args.get("dept"),
                                     include_inactive=request.args.get("includeInactive") in ("1", "true")))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_quick_reply(property_id: str):
    with db_session() as db:
        return ok(QuickReplyOut.model_validate(quick_replies.create(db, g.property_id, parse_body(QuickReplyIn))), 201)


@bp.patch("/<quick_reply_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def update_quick_reply(property_id: str, quick_reply_id: str):
    with db_session() as db:
        return ok(QuickReplyOut.model_validate(quick_replies.update(db, g.property_id, quick_reply_id, parse_body(QuickReplyPatch))))


@bp.delete("/<quick_reply_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def delete_quick_reply(property_id: str, quick_reply_id: str):
    with db_session() as db:
        quick_replies.delete(db, g.property_id, quick_reply_id)
    return no_content()


@bp.post("/<quick_reply_id>/render")
@require_auth
@require_property
@require_capability("reply")
def render_quick_reply(property_id: str, quick_reply_id: str):
    body = parse_body(RenderRequest)
    with db_session() as db:
        return ok(quick_replies.render(db, g.property_id, quick_reply_id, body.conversation_id, g.user.id))
```

`app/api/assets.py` — same shape: `GET ""` (any member; `?includeInactive=`), `POST ""`, `PATCH /<asset_id>`, `DELETE /<asset_id>` all `manage_admin` except GET, url_prefix `/api/p/<property_id>/assets`, using `assets.list/create/update/delete` and `AssetOut`.

`app/api/categories.py` — same shape with url_prefix `/api/p/<property_id>/resolution-categories`, `categories.list_tree/create/update/delete`, `CategoryOut`.

`app/api/short_links.py`:
```python
from flask import Blueprint, redirect

from app.api._util import db_session
from app.domain import assets
from app.errors import NotFound

bp = Blueprint("short_links", __name__)


@bp.get("/a/<short_code>")
def resolve(short_code: str):
    with db_session() as db:
        a = assets.get_by_short_code(db, short_code)
        if a is None:
            raise NotFound("Link not found")
        return redirect(a.url, code=302)
```

Register all four in `create_app`.

- [ ] **Step 7: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): quick replies with render, digital assets with short links, resolution categories"
```

---

