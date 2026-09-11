from flask import Blueprint, g, request

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
)

bp = Blueprint("work_orders", __name__, url_prefix="/api/p/<property_id>/work-orders")
CLOSING = {WorkOrderStatus.complete, WorkOrderStatus.verified, WorkOrderStatus.cancelled}


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
        return ok(work_orders.detail(db, g.property_id, work_order_id))


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
        return ok(work_orders.detail(db, g.property_id, work_order_id))
