from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.permissions import has_capability
from app.domain import audit
from app.domain._patch import patch_changes
from app.errors import Conflict, NotFound, ValidationFailed
from app.models import (
    Conversation,
    Department,
    DigitalAsset,
    PropertyMembership,
    QuickReply,
    UserAccount,
    WorkOrder,
)
from app.schemas.enums import Role
from app.schemas.users import (
    CreateStaffRequest,
    DepartmentIn,
    DepartmentOut,
    DepartmentPatch,
    StaffPatch,
    StaffUserOut,
)


def list_departments(db: Session, property_id: str) -> list[DepartmentOut]:
    rows = db.scalars(
        select(Department).where(Department.property_id == property_id).order_by(Department.name)
    ).all()
    return [DepartmentOut.model_validate(d) for d in rows]


def get_department(db: Session, property_id: str, department_id: str) -> Department:
    d = db.scalar(select(Department).where(Department.id == department_id,
                                           Department.property_id == property_id))
    if d is None:
        raise NotFound("Department not found")
    return d


def create_department(db: Session, property_id: str, data: DepartmentIn) -> Department:
    d = Department(property_id=property_id, **data.model_dump())
    db.add(d)
    db.flush()
    return d


def update_department(db: Session, property_id: str, department_id: str,
                      data: DepartmentPatch) -> Department:
    d = get_department(db, property_id, department_id)
    for k, v in patch_changes(Department, data).items():
        setattr(d, k, v)
    db.flush()
    return d


# Every nullable FK to department.id, with the message the admin sees if it still points here.
# Phase 1 does not soft-delete (design.md line 86) and these columns have no ON DELETE behaviour,
# so a delete that went through would either fail at the constraint or silently orphan the
# reference — e.g. null out a work order's owning department. Deactivating the department
# (active=False) is the escape hatch, so every message says so.
_DEPARTMENT_REFERENCES = (
    (PropertyMembership.department_id, "Move the staff members in this department to another one"),
    (QuickReply.department_id, "Reassign the quick replies in this department"),
    (DigitalAsset.department_id, "Reassign the digital assets in this department"),
    (Conversation.assigned_department_id, "Reassign the conversations assigned to this department"),
    (WorkOrder.department_id, "Reassign the work orders assigned to this department"),
)


def delete_department(db: Session, property_id: str, department_id: str) -> None:
    d = get_department(db, property_id, department_id)
    for column, fix in _DEPARTMENT_REFERENCES:
        if db.scalar(select(column).where(column == d.id).limit(1)):
            raise Conflict(f"{fix} first, or deactivate the department instead")
    db.delete(d)


def list_staff(db: Session, property_id: str) -> list[StaffUserOut]:
    rows = db.execute(
        select(UserAccount, PropertyMembership)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .where(PropertyMembership.property_id == property_id)
        .order_by(UserAccount.first_name, UserAccount.last_name)
    ).all()
    return [
        StaffUserOut(id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name,
                     avatar_url=u.avatar_url, role=m.role, department_id=m.department_id,
                     status=u.status.value)
        for u, m in rows
    ]


def members_of_department(db: Session, property_id: str, department_id: str) -> list[str]:
    return list(
        db.scalars(
            select(PropertyMembership.user_id).where(
                PropertyMembership.property_id == property_id,
                PropertyMembership.department_id == department_id,
            )
        ).all()
    )


def _staff_out(db: Session, property_id: str, user_id: str) -> StaffUserOut:
    row = db.execute(select(UserAccount, PropertyMembership)
                     .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
                     .where(PropertyMembership.property_id == property_id,
                            UserAccount.id == user_id)).first()
    if row is None:
        raise NotFound("User is not a member of this property")
    u, m = row
    return StaffUserOut(id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name,
                        avatar_url=u.avatar_url,
                        role=m.role, department_id=m.department_id, status=u.status.value)


def _check_department(db: Session, property_id: str, department_id: str | None) -> None:
    if department_id and not db.scalar(select(Department.id).where(
            Department.id == department_id, Department.property_id == property_id)):
        raise ValidationFailed("Unknown department")


def create_staff(db: Session, property_id: str, actor_user_id: str,
                 data: CreateStaffRequest) -> StaffUserOut:
    _check_department(db, property_id, data.department_id)
    user = db.scalar(select(UserAccount).where(UserAccount.email == data.email.lower()))
    if user is None:
        if not data.password:
            raise ValidationFailed("A password is required for a new account")
        try:
            with db.begin_nested():
                user = UserAccount(email=data.email.lower(), first_name=data.first_name,
                                   last_name=data.last_name,
                                   phone=data.phone, password_hash=hash_password(data.password))
                db.add(user)
                db.flush()
        except IntegrityError:
            user = db.scalar(select(UserAccount).where(UserAccount.email == data.email.lower()))
    if db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.user_id == user.id,
            PropertyMembership.property_id == property_id)):
        raise Conflict("Already a member of this property")
    db.add(PropertyMembership(user_id=user.id, property_id=property_id, role=data.role,
                              department_id=data.department_id))
    db.flush()
    audit.record(db, property_id, actor_user_id, "membership.created", "user_account", user.id,
                 after={"role": data.role.value, "department_id": data.department_id})
    return _staff_out(db, property_id, user.id)


ADMIN_ROLES = [r for r in Role if has_capability(r, "manage_admin")]


def _assert_not_last_admin(db: Session, property_id: str, m: PropertyMembership,
                           new_role: Role | None = None) -> None:
    """A property must keep at least one membership that can `manage_admin`.

    `corporate` is a per-property role like any other, not a cross-property escape hatch, so
    dropping the last one leaves the property with nobody who can add staff back — an in-app
    lockout with no in-app remedy.
    """
    if m.role not in ADMIN_ROLES or (new_role is not None and new_role in ADMIN_ROLES):
        return
    if not db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.property_id == property_id,
            PropertyMembership.role.in_(ADMIN_ROLES),
            PropertyMembership.id != m.id)):
        raise Conflict("This property would be left with no administrator")


def update_staff(db: Session, property_id: str, actor_user_id: str, user_id: str,
                data: StaffPatch) -> StaffUserOut:
    m = db.scalar(select(PropertyMembership).where(PropertyMembership.user_id == user_id,
                                                   PropertyMembership.property_id == property_id))
    if m is None:
        raise NotFound("User is not a member of this property")
    before = {"role": m.role.value, "department_id": m.department_id}
    changes = data.model_dump(exclude_unset=True)
    if "department_id" in changes:
        _check_department(db, property_id, changes["department_id"])
        m.department_id = changes["department_id"]
    if data.role is not None:
        _assert_not_last_admin(db, property_id, m, new_role=data.role)
        m.role = data.role
    db.flush()
    audit.record(db, property_id, actor_user_id, "membership.updated", "user_account", user_id,
                 before=before,
                 after={"role": m.role.value, "department_id": m.department_id})
    return _staff_out(db, property_id, user_id)


def remove_membership(db: Session, property_id: str, actor_user_id: str, user_id: str) -> None:
    m = db.scalar(select(PropertyMembership).where(PropertyMembership.user_id == user_id,
                                                   PropertyMembership.property_id == property_id))
    if m is None:
        raise NotFound("User is not a member of this property")
    _assert_not_last_admin(db, property_id, m)
    db.delete(m)
    audit.record(db, property_id, actor_user_id, "membership.removed", "user_account", user_id)
