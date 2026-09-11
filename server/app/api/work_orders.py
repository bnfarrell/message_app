from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import conversations, work_orders
from app.errors import Forbidden, ValidationFailed
from app.schemas.enums import WorkOrderStatus
from app.schemas.work_orders import (
    CreateWorkOrder,
    WorkOrderListQuery,
    WorkOrderOut,
    WorkOrderPatch,
    WorkOrderPhotoUpload,
)

bp = Blueprint("work_orders", __name__, url_prefix="/api/p/<property_id>/work-orders")
CLOSING = {WorkOrderStatus.complete, WorkOrderStatus.verified, WorkOrderStatus.cancelled}
# Multipart framing — boundaries and part headers — around a photo at the cap. Generous, because
# this only decides whether the body is worth reading at all; work_orders.attach_photo re-checks
# the bytes themselves, which is the check that counts.
MULTIPART_OVERHEAD_BYTES = 4096


@bp.get("")
@require_auth
@require_property
def list_work_orders(property_id: str):
    q = parse_query(WorkOrderListQuery)
    with db_session() as db:
        return ok(work_orders.list(db, g.property_id, status=q.status, type=q.type, dept=q.dept,
                                   assignee=q.assignee, mine_user_id=g.user.id if q.mine else None,
                                   include_closed=q.include_closed))


@bp.get("/prefill")
@require_auth
@require_property
@require_capability("create_work_order")
def prefill(property_id: str):
    conversation_id = request.args.get("conversationId")
    if not conversation_id:
        raise ValidationFailed("conversationId is required")
    with db_session() as db:
        conversations.get_for_viewer(db, g.property_id, conversation_id, g.membership.role,
                                     g.user.id, g.membership.department_id)
        return ok(work_orders.prefill_from_conversation(db, g.property_id, conversation_id))


@bp.post("")
@require_auth
@require_property
@require_capability("create_work_order")
def create_work_order(property_id: str):
    data = parse_body(CreateWorkOrder)
    with db_session() as db:
        if data.source_conversation_id:
            conversations.get_for_viewer(db, g.property_id, data.source_conversation_id,
                                         g.membership.role, g.user.id, g.membership.department_id)
        wo = work_orders.create(db, g.property_id, g.user.id, data)
        return ok(WorkOrderOut.model_validate(wo), 201)


@bp.get("/<work_order_id>")
@require_auth
@require_property
def get_work_order(property_id: str, work_order_id: str):
    with db_session() as db:
        return ok(work_orders.detail(db, g.property_id, work_order_id,
                                     viewer_role=g.membership.role, viewer_user_id=g.user.id,
                                     viewer_department_id=g.membership.department_id))


@bp.post("/<work_order_id>/photos")
@require_auth
@require_property
def add_work_order_photo(property_id: str, work_order_id: str):
    """multipart/form-data: a `photo` file part and a `kind` field of "before" or "after".

    No capability gate, deliberately: PATCH above carries none either beyond `close_work_order`
    for a closing status, so attaching a photo is gated exactly like leaving a comment on the
    same work order. Inventing a capability here would put this route out of step with the one
    beside it.
    """
    # Before request.form or request.files, either of which makes Werkzeug read the whole body.
    # Content-Length is the client's claim, so this only avoids buffering an obviously oversized
    # upload; the authoritative check is on the bytes.
    if (request.content_length or 0) > work_orders.MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(
            f"A photo must be {work_orders.MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    meta = parse_body(WorkOrderPhotoUpload)
    upload = request.files.get("photo")
    if upload is None:
        raise ValidationFailed("A photo file is required", details={"photo": "required"})
    # cap + 1 is enough to know it is over the cap without holding any more of it than that.
    data = upload.read(work_orders.MAX_PHOTO_BYTES + 1)
    with db_session() as db:
        return ok(work_orders.attach_photo(db, g.property_id, work_order_id, g.user.id,
                                           kind=meta.kind, data=data), 201)


@bp.get("/<work_order_id>/photos/<photo_id>")
@require_auth
@require_property
def get_work_order_photo(property_id: str, work_order_id: str, photo_id: str):
    with db_session() as db:
        photo = work_orders.get_photo(db, g.property_id, work_order_id, photo_id)
        body, content_type = photo.data, photo.content_type
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        # The stored bytes are what a sniffing browser must not reinterpret, and nothing may
        # replace a photo once attached, so it can be cached for as long as the session lasts.
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })


@bp.patch("/<work_order_id>")
@require_auth
@require_property
def patch_work_order(property_id: str, work_order_id: str):
    p = parse_body(WorkOrderPatch)
    with db_session() as db:
        if p.assigned_user_id or p.department_id or p.clear_assignee:
            work_orders.assign(db, g.property_id, work_order_id, g.user.id,
                               user_id=p.assigned_user_id,
                               department_id=p.department_id, clear=p.clear_assignee)
        if p.priority is not None:
            work_orders.set_priority(db, g.property_id, work_order_id, g.user.id, p.priority)
        if p.status is not None:
            if p.status in CLOSING and not has_capability(g.membership.role, "close_work_order"):
                raise Forbidden("Your role cannot close work orders")
            work_orders.transition(db, g.property_id, work_order_id, g.user.id, p.status,
                                   comment=p.comment)
        elif p.comment:
            work_orders.comment(db, g.property_id, work_order_id, g.user.id, p.comment)
        return ok(work_orders.detail(db, g.property_id, work_order_id,
                                     viewer_role=g.membership.role, viewer_user_id=g.user.id,
                                     viewer_department_id=g.membership.department_id))
