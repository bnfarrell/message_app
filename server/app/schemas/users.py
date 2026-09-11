from pydantic import EmailStr, Field

from app.schemas.common import CamelModel
from app.schemas.conversations import GuestOut, StayOut
from app.schemas.enums import DepartmentType, Role


class DepartmentIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    type: DepartmentType
    escalation_minutes: int = Field(default=15, gt=0)
    active: bool = True


class DepartmentPatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: DepartmentType | None = None
    escalation_minutes: int | None = Field(default=None, gt=0)
    active: bool | None = None


class DepartmentOut(CamelModel):
    id: str
    name: str
    type: DepartmentType
    escalation_minutes: int
    active: bool


class StaffUserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    role: Role
    department_id: str | None = None
    status: str


class CreateStaffRequest(CamelModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: Role
    department_id: str | None = None
    phone: str | None = None


class StaffPatch(CamelModel):
    """Per-property membership fields only.

    `UserAccount` is global and one account may hold memberships at several properties, so an
    endpoint authorised by a membership at the property in the URL must never write global
    columns (password, status, name): an admin at one property could otherwise reset the password
    of an account that is also an admin somewhere else and inherit its access everywhere. Revoking
    a person's access to *this* property is DELETE /users/<id> (the membership), not a global
    account disable.
    """

    role: Role | None = None
    department_id: str | None = None


class GuestDetail(CamelModel):
    guest: GuestOut
    stays: list[StayOut]
    conversation_ids: list[str]
