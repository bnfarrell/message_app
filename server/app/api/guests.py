from flask import Blueprint, g
from sqlalchemy import select

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import guests
from app.errors import NotFound
from app.models import Conversation, Stay
from app.schemas.conversations import GuestOut, StayOut
from app.schemas.users import GuestDetail

bp = Blueprint("guests", __name__, url_prefix="/api/p/<property_id>/guests")


@bp.get("/<guest_id>")
@require_auth
@require_property
@require_capability("view_all_conversations")
def get_guest(property_id: str, guest_id: str):
    """Returns the guest's phone number, consent status, stay history and conversation ids, which
    is strictly more than a dept_staff member can read through the conversation routes — and
    `view_all_conversations` is the capability dept_staff correctly lacks."""
    with db_session() as db:
        guest = guests.get(db, g.property_id, guest_id)
        if guest is None:
            raise NotFound("Guest not found")
        stays = db.scalars(select(Stay).where(Stay.guest_id == guest.id)
                          .order_by(Stay.arrival_date.desc())).all()
        conv_ids = [*db.scalars(
            select(Conversation.id).where(Conversation.guest_id == guest.id)).all()]
        return ok(GuestDetail(guest=GuestOut.model_validate(guest),
                              stays=[StayOut.model_validate(s) for s in stays],
                              conversation_ids=conv_ids))
