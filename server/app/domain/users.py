from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.permissions import has_capability
from app.domain import audit
from app.errors import Conflict, NotFound, ValidationFailed
from app.models import Department, PropertyMembership, UserAccount
from app.schemas.enums import Role
from app.schemas.users import (
    CreateStaffRequest,
    DepartmentOut,
    StaffPatch,
    StaffUserOut,
)


def list_departments(db: Session, property_id: str) -> list[DepartmentOut]:
    rows = db.scalars(
        select(Department).where(Department.property_id == property_id).order_by(Department.name)
    ).all()
    return [DepartmentOut.model_validate(d) for d in rows]


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
