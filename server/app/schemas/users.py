from pydantic import EmailStr, Field

from app.schemas.common import CamelModel
from app.schemas.conversations import GuestOut, StayOut
from app.schemas.enums import DepartmentType, Role, UserStatus


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
    role: Role | None = None
    department_id: str | None = None
    status: UserStatus | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    first_name: str | None = None
    last_name: str | None = None


class GuestDetail(CamelModel):
    guest: GuestOut
    stays: list[StayOut]
    conversation_ids: list[str]
