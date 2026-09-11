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
