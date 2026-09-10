from app.schemas.common import CamelModel
from app.schemas.enums import DepartmentType, Role


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
