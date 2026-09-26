from enum import StrEnum


class Role(StrEnum):
    agent = "agent"
    dept_staff = "dept_staff"
    supervisor = "supervisor"
    manager = "manager"
    admin = "admin"
    corporate = "corporate"


class UserStatus(StrEnum):
    active = "active"
    disabled = "disabled"


class DepartmentType(StrEnum):
    front_desk = "front_desk"
    housekeeping = "housekeeping"
    engineering = "engineering"
    food_beverage = "food_beverage"
    spa = "spa"
    security = "security"
    valet = "valet"
    other = "other"


class SmsConsentStatus(StrEnum):
    unknown = "unknown"
    opted_in = "opted_in"
    opted_out = "opted_out"


class StayStatus(StrEnum):
    reserved = "reserved"
    checked_in = "checked_in"
    checked_out = "checked_out"
    cancelled = "cancelled"
    no_show = "no_show"


class ConversationStatus(StrEnum):
    open = "open"
    snoozed = "snoozed"
    archived = "archived"


class Channel(StrEnum):
    sms = "sms"
    web = "web"
    whatsapp = "whatsapp"
    email = "email"


class Direction(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class AuthorType(StrEnum):
    guest = "guest"
    staff = "staff"
    system = "system"
    automation = "automation"


class DeliveryStatus(StrEnum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    undelivered = "undelivered"


class WorkOrderType(StrEnum):
    maintenance = "maintenance"
    housekeeping = "housekeeping"
    guest_request = "guest_request"
    pm = "pm"
    other = "other"


class Priority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class WorkOrderStatus(StrEnum):
    open = "open"
    assigned = "assigned"
    in_progress = "in_progress"
    blocked = "blocked"
    complete = "complete"
    verified = "verified"
    cancelled = "cancelled"


class LocationType(StrEnum):
    room = "room"
    public_area = "public_area"
    equipment = "equipment"
    other = "other"


class WorkOrderEventType(StrEnum):
    created = "created"
    status_changed = "status_changed"
    assigned = "assigned"
    commented = "commented"
    priority_changed = "priority_changed"
    photo_attached = "photo_attached"


class WorkOrderPhotoKind(StrEnum):
    before = "before"
    after = "after"


class DraftPromptStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    dismissed = "dismissed"


class AssetType(StrEnum):
    file = "file"
    link = "link"
    menu = "menu"
    map = "map"
    form = "form"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    dead = "dead"


class StaffConversationKind(StrEnum):
    dm = "dm"
    group = "group"
    all = "all"


class Shift(StrEnum):
    am = "am"
    pm = "pm"
    overnight = "overnight"


class MentionTargetType(StrEnum):
    user = "user"
    department = "department"


class PmUnitKind(StrEnum):
    guest_room = "guest_room"
    common_area = "common_area"
    equipment = "equipment"


class PmUnitSource(StrEnum):
    manual = "manual"
    csv = "csv"
    pms = "pms"


class PmTemplateMode(StrEnum):
    sweep = "sweep"
    scheduled = "scheduled"


class PmCadence(StrEnum):
    monthly = "monthly"
    quarterly = "quarterly"
    semiannual = "semiannual"
    annual = "annual"


class PmItemType(StrEnum):
    checkbox = "checkbox"
    text = "text"
    number = "number"
    photo = "photo"


class PmCycleStatus(StrEnum):
    open = "open"
    closed = "closed"


class PmRunStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    passed = "passed"
    failed = "failed"
    missed = "missed"


class HkStatus(StrEnum):
    """`clean` = the housekeeper finished and it awaits inspection; `inspected` = a supervisor
    passed it (spec §2.1)."""
    clean = "clean"
    dirty = "dirty"
    in_progress = "in_progress"
    inspected = "inspected"
    out_of_order = "out_of_order"
    out_of_service = "out_of_service"


class HkServiceType(StrEnum):
    departure = "departure"
    stayover = "stayover"
    touch_up = "touch_up"


class HkAssignmentStatus(StrEnum):
    assigned = "assigned"
    in_progress = "in_progress"
    done = "done"
    passed = "passed"


class RoomEventType(StrEnum):
    status_changed = "status_changed"
    assigned = "assigned"
    reassigned = "reassigned"
    unassigned = "unassigned"
    started = "started"
    completed = "completed"
    inspection_passed = "inspection_passed"
    inspection_failed = "inspection_failed"
    marked_dirty = "marked_dirty"
    rush_set = "rush_set"
    rush_cleared = "rush_cleared"


class HkOccupancy(StrEnum):
    """Derived per request from `stay`, never stored (spec §2.1)."""
    vacant = "vacant"
    arrival = "arrival"
    stayover = "stayover"
    departure = "departure"


class ChecklistSchedule(StrEnum):
    weekly = "weekly"
    on_demand = "on_demand"


class ChecklistStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    complete = "complete"
    missed = "missed"


class LogFieldType(StrEnum):
    short_text = "short_text"
    long_text = "long_text"
    integer = "integer"
    decimal = "decimal"
    percent = "percent"
