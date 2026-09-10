from pydantic import EmailStr, Field

from app.schemas.common import CamelModel
from app.schemas.enums import Role


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    locale: str


class MembershipOut(CamelModel):
    property_id: str
    property_name: str
    property_code: str
    role: Role
    department_id: str | None = None


class SessionOut(CamelModel):
    user: UserOut
    memberships: list[MembershipOut]
