from flask import Blueprint, Response, g, request

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_property
from app.domain import staff_messages
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import ValidationFailed
from app.schemas.staff_messages import (
    AddParticipantsRequest,
    CreateStaffConversationRequest,
    GroupPatch,
    SendStaffMessageRequest,
    StaffMessageOut,
)

bp = Blueprint("staff_messages", __name__, url_prefix="/api/p/<property_id>/staff-conversations")
directory_bp = Blueprint("staff_directory", __name__, url_prefix="/api/p/<property_id>")


@bp.get("")
@require_auth
@require_property
def list_conversations(property_id: str):
    with db_session() as db:
        return ok(staff_messages.list_conversations_for_user(db, g.property_id, g.user.id))


@bp.post("")
@require_auth
@require_property
def create_conversation(property_id: str):
    data = parse_body(CreateStaffConversationRequest)
    with db_session() as db:
        conv, created = staff_messages.create_conversation(db, g.property_id, g.user.id, data)
        out = staff_messages.detail(db, g.property_id, conv.id, g.user.id)
        return ok(out, 201 if created else 200)


@bp.get("/<conversation_id>")
@require_auth
@require_property
def get_conversation(property_id: str, conversation_id: str):
    with db_session() as db:
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


MULTIPART_OVERHEAD_BYTES = 4096  # matches work_orders.py's rationale exactly


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
def send_message(property_id: str, conversation_id: str):
    if (request.content_length or 0) > MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    data = parse_body(SendStaffMessageRequest)
    upload = request.files.get("photo")
    photo_bytes = None
    content_type = None
    if upload is not None:
        photo_bytes = upload.read(MAX_PHOTO_BYTES + 1)
        if len(photo_bytes) > MAX_PHOTO_BYTES:
            raise ValidationFailed(
                f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
                details={"photo": "file_too_large"})
        content_type = sniff_image_type(photo_bytes)
        if content_type is None:
            raise ValidationFailed("A photo must be a JPEG, PNG or WebP image",
                                   details={"photo": "unsupported_image_type"})
    with db_session() as db:
        msg = staff_messages.send_message(db, g.property_id, conversation_id, g.user.id,
                                          body=data.body, photo_content_type=content_type,
                                          photo_byte_size=len(photo_bytes) if photo_bytes else None,
                                          photo_data=photo_bytes)
        author = g.user
        return ok(StaffMessageOut(
            id=msg.id, conversation_id=msg.conversation_id, author_user_id=msg.author_user_id,
            author_name=f"{author.first_name} {author.last_name}", body=msg.body,
            photo_url=(staff_messages.photo_url(g.property_id, conversation_id, msg.id)
                      if content_type else None),
            created_at=msg.created_at), 201)


@bp.get("/<conversation_id>/messages/<message_id>/photo")
@require_auth
@require_property
def get_message_photo(property_id: str, conversation_id: str, message_id: str):
    with db_session() as db:
        staff_messages.get_for_participant(db, g.property_id, conversation_id, g.user.id)
        msg = staff_messages.get_message_photo(db, g.property_id, conversation_id, message_id)
        body, content_type = msg.photo_data, msg.photo_content_type
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })


@bp.post("/<conversation_id>/read")
@require_auth
@require_property
def mark_read(property_id: str, conversation_id: str):
    with db_session() as db:
        staff_messages.mark_read(db, g.property_id, conversation_id, g.user.id)
    return no_content()


@bp.patch("/<conversation_id>")
@require_auth
@require_property
def patch_conversation(property_id: str, conversation_id: str):
    data = parse_body(GroupPatch)
    with db_session() as db:
        staff_messages.update_group(db, g.property_id, conversation_id, g.user.id, data)
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


@bp.post("/<conversation_id>/participants")
@require_auth
@require_property
def add_participants(property_id: str, conversation_id: str):
    data = parse_body(AddParticipantsRequest)
    with db_session() as db:
        staff_messages.add_participants(db, g.property_id, conversation_id, g.user.id, data)
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


@bp.delete("/<conversation_id>/participants/<user_id>")
@require_auth
@require_property
def remove_participant(property_id: str, conversation_id: str, user_id: str):
    with db_session() as db:
        staff_messages.remove_participant(db, g.property_id, conversation_id, g.user.id, user_id)
        # The remover themself may be the one leaving — detail() would then 404 for them, so
        # only re-fetch when someone else was removed.
        if user_id == g.user.id:
            return no_content()
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


@directory_bp.get("/staff-directory")
@require_auth
@require_property
def get_directory(property_id: str):
    with db_session() as db:
        return ok(staff_messages.directory(db, g.property_id, g.user.id))
