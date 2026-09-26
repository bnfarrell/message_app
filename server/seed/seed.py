"""Deterministic development seed. `flask seed` or `python -m seed.seed`. Matches spec §8.

Determinism covers the shape and content of the seeded data (names, counts, message bodies, phone
numbers, timing, etc.) — all driven from `random.Random(42)`, so two runs produce identical data
(ids aside, since those are `uuid.uuid4()`). It deliberately does NOT cover
`DigitalAsset.short_code`: those come from `app.domain.assets.new_short_code`, which uses
`secrets.choice`, not this module's seeded RNG, because a short code is the public, guest-facing
`/a/<code>` URL sent over SMS — making it predictable to satisfy a determinism goal would be a real
security regression. Short codes differ between seed runs; everything else does not.
"""
from __future__ import annotations

import base64
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app import clock
from app.auth.passwords import hash_password
from app.db import Database, run_migrations
from app.domain import (
    hk_assignments,
    hk_photos,
    hk_rooms,
    hk_tick,
    hk_transitions,
    pm_cycles,
    staff_messages,
)
from app.domain.assets import new_short_code
from app.domain.log import shift_for
from app.models import (
    Conversation,
    Department,
    DigitalAsset,
    DraftPrompt,
    Guest,
    HousekeepingAssignment,
    InternalNote,
    LogEntry,
    LogEntryMention,
    MaintainableUnit,
    Message,
    PmCycle,
    PmRun,
    PmRunAnswer,
    PmRunPhoto,
    PmTemplate,
    PmTemplateItem,
    PmTemplateUnit,
    Property,
    PropertyMembership,
    QuickReply,
    ResolutionCategory,
    Room,
    Stay,
    UserAccount,
    WorkOrder,
    WorkOrderEvent,
)
from app.queue import jobs
from app.schemas.enums import (
    AssetType,
    AuthorType,
    Channel,
    ConversationStatus,
    DeliveryStatus,
    DepartmentType,
    Direction,
    DraftPromptStatus,
    HkServiceType,
    HkStatus,
    LocationType,
    MentionTargetType,
    PmCadence,
    PmCycleStatus,
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
    PmUnitSource,
    Priority,
    Role,
    SmsConsentStatus,
    StayStatus,
    WorkOrderEventType,
    WorkOrderStatus,
    WorkOrderType,
)
from seed import data
from seed.pm_units import unit_rows

PASSWORD = "Password123!"

# A 1×1 transparent PNG: enough for a seeded run's required photo item to hold a real image
# the checklist page can render, without shipping picture files in the seed.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@dataclass
class SeedSummary:
    properties: int
    users: int
    guests: int
    stays: int
    conversations: int
    messages: int
    work_orders: int
    log_entries: int
    maintainable_units: int
    pm_templates: int
    pm_runs: int
    rooms: int
    hk_assignments: int


def _phone(rng: random.Random, used: set[str]) -> str:
    while True:
        p = f"+1555{rng.randint(1000000, 9999999)}"
        if p not in used and not p.endswith("0000"):
            used.add(p)
            return p


def run(database_url: str, *, reset: bool = True, now: datetime | None = None) -> SeedSummary:
    now = now or clock.now()
    today = now.date()
    rng = random.Random(42)
    if reset:
        if not database_url.startswith("sqlite:///"):
            # Deleting a file only makes sense for the sqlite dev database. For any other URL
            # (Postgres, etc.) there is no safe way to "reset" here without risking a production
            # database, so refuse rather than silently seeding on top of existing data.
            raise ValueError(
                "reset=True is only supported for sqlite:/// URLs; pass reset=False for other "
                "databases and ensure the target database is empty before seeding."
            )
        path = Path(database_url.removeprefix("sqlite:///"))
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(database_url)
    database = Database(database_url)
    used_phones: set[str] = set()

    with database.session() as db:
        # ---- properties & departments
        hvh = Property(name="Harbourview Hotel", code="HVH", timezone="America/New_York",
                       sms_number="+15550100", address="1 Harbour St", currency="USD",
                       primary_color="#f0b323",
                       settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                                 "help_text": "Harbourview Hotel: text us anytime, or call "
                                             "+1 555 0100."})
        lsi = Property(name="Lakeside Inn", code="LSI", timezone="America/Chicago",
                       sms_number="+15550200",
                       settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                                 "help_text": "Lakeside Inn: call +1 555 0200."})
        db.add_all([hvh, lsi])
        db.flush()
        depts = {}
        for name, typ in [("Front Desk", DepartmentType.front_desk),
                          ("Housekeeping", DepartmentType.housekeeping),
                          ("Engineering", DepartmentType.engineering)]:
            d = Department(property_id=hvh.id, name=name, type=typ)
            db.add(d)
            depts[typ.value] = d
        lsi_fd = Department(property_id=lsi.id, name="Front Desk", type=DepartmentType.front_desk)
        db.add(lsi_fd)
        db.flush()

        # ---- staff (12 at HVH + 2 at LSI)
        pw = hash_password(PASSWORD, rounds=10)

        def user(email, first, last):
            u = UserAccount(email=email, first_name=first, last_name=last, password_hash=pw)
            db.add(u)
            db.flush()
            return u

        def member(u, prop, role, dept=None):
            db.add(PropertyMembership(user_id=u.id, property_id=prop.id, role=role,
                                      department_id=dept.id if dept else None))

        staff = {
            "ava": user("ava@hvh.test", "Ava", "Agent"),
            "marcus": user("marcus@hvh.test", "Marcus", "Reyes"),
            "jordan": user("jordan@hvh.test", "Jordan", "Tate"),
            "hana": user("hana@hvh.test", "Hana", "Keeper"),
            "rosa": user("rosa@hvh.test", "Rosa", "Lima"),
            "eli": user("eli@hvh.test", "Eli", "Engineer"),
            "noah": user("noah@hvh.test", "Noah", "Fix"),
            "hk_sup": user("hk.supervisor@hvh.test", "Grace", "Osei"),
            "sam": user("sam@hvh.test", "Sam", "Super"),
            "morgan": user("morgan@hvh.test", "Morgan", "Manager"),
            "alex": user("alex@hvh.test", "Alex", "Admin"),
            "casey": user("casey@group.test", "Casey", "Corp"),
        }
        member(staff["ava"], hvh, Role.agent, depts["front_desk"])
        member(staff["marcus"], hvh, Role.agent, depts["front_desk"])
        member(staff["jordan"], hvh, Role.agent, depts["front_desk"])
        member(staff["hana"], hvh, Role.dept_staff, depts["housekeeping"])
        member(staff["rosa"], hvh, Role.dept_staff, depts["housekeeping"])
        member(staff["eli"], hvh, Role.dept_staff, depts["engineering"])
        member(staff["noah"], hvh, Role.dept_staff, depts["engineering"])
        member(staff["hk_sup"], hvh, Role.supervisor, depts["housekeeping"])
        member(staff["sam"], hvh, Role.supervisor, depts["engineering"])
        member(staff["morgan"], hvh, Role.manager)
        member(staff["alex"], hvh, Role.admin)
        member(staff["casey"], hvh, Role.corporate)
        blake = user("blake@lsi.test", "Blake", "Admin")
        member(blake, lsi, Role.admin)
        bea = user("bea@lsi.test", "Bea", "Agent")
        member(bea, lsi, Role.agent, lsi_fd)
        member(staff["casey"], lsi, Role.corporate)

        # ---- rooms, guests, stays
        rooms = [f"{f}{n:02d}" for f in range(1, 7) for n in range(1, 21)]
        rng.shuffle(rooms)
        guests: list[Guest] = []
        stays: list[Stay] = []

        def make_guest(prop, first=None, last=None, phone=None, tier=None,
                       consent=SmsConsentStatus.opted_in):
            g = Guest(property_id=prop.id, first_name=first or rng.choice(data.FIRST_NAMES),
                      last_name=last or rng.choice(data.LAST_NAMES),
                      phone_e164=phone or _phone(rng, used_phones),
                      loyalty_tier=tier if tier is not None else rng.choice(data.LOYALTY),
                      vip=rng.random() < 0.05, sms_consent_status=consent,
                      sms_consent_at=now - timedelta(days=rng.randint(1, 400)),
                      sms_consent_source="pms")
            db.add(g)
            db.flush()
            guests.append(g)
            return g

        def make_stay(g, room, status, arrival, nights, res_id=None):
            # `stay_count` and `is_return_guest` are set from the rows that actually exist, in
            # one pass once every stay has been created (see below).
            departure = arrival + timedelta(days=nights)
            s = Stay(guest_id=g.id, property_id=g.property_id,
                     pms_reservation_id=res_id or f"RES-{room}-{rng.randint(1000, 9999)}",
                     room_number=room, room_type=rng.choice(data.ROOM_TYPES),
                     rate_code=rng.choice(data.RATE_CODES),
                     status=status, arrival_date=arrival, departure_date=departure,
                     adults=rng.choice([1, 2, 2, 2, 3]), children=rng.choice([0, 0, 0, 1, 2]),
                     actual_checkin_at=(datetime.combine(arrival, datetime.min.time(), tzinfo=UTC)
                                        + timedelta(hours=15))
                     if status != StayStatus.reserved else None,
                     # Anchored to the departure date rather than to `now`: a stay that ended a
                     # year ago must not claim it checked out yesterday.
                     actual_checkout_at=(datetime.combine(departure, datetime.min.time(),
                                                          tzinfo=UTC) + timedelta(hours=11))
                     if status == StayStatus.checked_out else None,
                     raw_pms={"seed": True})
            db.add(s)
            db.flush()
            stays.append(s)
            return s

        sarah = make_guest(hvh, "Sarah", "Chen", "+15551234567", "Gold")
        make_stay(sarah, "412", StayStatus.checked_in, today - timedelta(days=1), 3,
                  res_id="RES-412")
        # fails delivery on purpose
        tom = make_guest(hvh, "Tom", "Becker", "+15552000000", "Silver")
        make_stay(tom, "516", StayStatus.checked_in, today, 2)
        room_iter = iter(r for r in rooms if r not in ("412", "516"))
        for _ in range(83):
            g = make_guest(hvh)
            make_stay(g, next(room_iter), StayStatus.checked_in,
                      today - timedelta(days=rng.randint(0, 4)), rng.randint(1, 5))
        for _ in range(10):
            g = make_guest(hvh)
            make_stay(g, next(room_iter), StayStatus.reserved, today, rng.randint(1, 4))
        departing = [s for s in stays if s.status == StayStatus.checked_in][2:12]
        for s in departing:
            s.departure_date = today
        for _ in range(7):  # + Lena below = 8 checked out
            g = make_guest(hvh)
            make_stay(g, rng.choice(rooms), StayStatus.checked_out, today - timedelta(days=3), 2)
        lena = make_guest(hvh, "Lena", "Park", "+15553104411", None, SmsConsentStatus.opted_out)
        lena.sms_consent_source = "sms_keyword"
        make_stay(lena, "301", StayStatus.checked_out, today - timedelta(days=4), 2)
        # Two repeat guests with a real history. Every guest had exactly one stay, so the guest
        # panel's "Previous stays" was empty for all of them — including Sarah, whose seeded
        # internal note says "Gold member, 4th stay". These rows make that note true.
        for days_ago, nights in ((421, 2), (250, 3), (96, 2)):
            make_stay(sarah, rng.choice(rooms), StayStatus.checked_out,
                      today - timedelta(days=days_ago), nights)
        make_stay(tom, rng.choice(rooms), StayStatus.checked_out,
                  today - timedelta(days=163), 1)
        for _ in range(6):
            g = make_guest(lsi)
            make_stay(g, str(rng.randint(101, 140)), StayStatus.checked_in, today, 2)

        # `stay_count` and `is_return_guest` are denormalised PMS fields the guest panel renders
        # ("4th stay") beside the stay list it renders from the rows. They were random, so 95 of
        # 106 stays claimed a repeat visit that no row backed. Derive both from the rows instead,
        # in one place, so the two can never disagree again.
        by_guest: dict[str, list[Stay]] = defaultdict(list)
        for s in stays:
            by_guest[s.guest_id].append(s)
        for guest_stays in by_guest.values():
            for n, s in enumerate(sorted(guest_stays, key=lambda x: (x.arrival_date, x.id)),
                                  start=1):
                s.stay_count = n
                s.is_return_guest = n > 1
        db.flush()

        # ---- staff messaging: everyone joins #ALL, admin posts a welcome message so the
        # screen isn't empty on first login (design.md §11.2 — seed data should produce
        # realistic density, not an empty state).
        all_channel = staff_messages.get_or_create_all_conversation(db, hvh.id)
        for key in ("ava", "marcus", "jordan", "hana", "rosa", "eli", "noah", "hk_sup", "sam",
                   "morgan", "alex", "casey"):
            staff_messages.ensure_participant(db, all_channel.id, staff[key].id)
        staff_messages.send_message(db, hvh.id, all_channel.id, staff["alex"].id,
                                    body="Welcome to Relay Messages — this channel reaches "
                                        "every member of the team.")

        # ---- hotel log: three entries for property A shaped to exercise the feature (spec
        # §3) rather than to look tidy — an am shift-handover, a pinned pm announcement, and
        # an overnight entry with an unacknowledged Housekeeping audience so the outstanding
        # list is real on first load. Dated yesterday so the shift classification (which
        # depends only on local time-of-day, spec §3.3) never lands in the future regardless
        # of when this seed happens to run.
        yesterday = today - timedelta(days=1)
        hvh_tz = ZoneInfo(hvh.timezone)

        def local_at(day, hour, minute=0):
            return datetime.combine(day, time(hour, minute), tzinfo=hvh_tz).astimezone(UTC)

        am_at = local_at(yesterday, 7, 30)
        am_entry = LogEntry(
            property_id=hvh.id, author_user_id=staff["ava"].id,
            department_id=depts["front_desk"].id, shift=shift_for(hvh, am_at),
            body=("AM CHECKLIST\nName: Ava Agent\n"
                  f"Date: {yesterday.month}/{yesterday.day}/{yesterday.year}\n"
                  "Shift Time: 7AM-3PM\n\n"
                  "Arrivals expected: 12\nArrivals actual: 11\n"
                  "Departures actual: 9\nDepartures left: 1\nOccupancy: 70.8%\n"
                  "Notes: 412 AC repaired overnight, confirmed cool this morning. 516 "
                  "requested late checkout to 1pm, approved.\n\n"
                  f"@[Housekeeping](department:{depts['housekeeping'].id}) please turn the 9 "
                  "departure rooms by noon — two are same-day sells."),
            created_at=am_at)
        db.add(am_entry)
        db.flush()
        db.add(LogEntryMention(log_entry_id=am_entry.id, property_id=hvh.id,
                               type=MentionTargetType.department,
                               target_id=depts["housekeeping"].id, position=0))

        pm_at = local_at(yesterday, 15, 30)
        db.add(LogEntry(
            property_id=hvh.id, author_user_id=staff["sam"].id,
            shift=shift_for(hvh, pm_at),
            body=("Corporate site visit tomorrow at 10am. Please have the lobby display area "
                  "cleared tonight and brief your teams before you leave."),
            pinned=True, pinned_by_user_id=staff["sam"].id, pinned_at=pm_at,
            created_at=pm_at))

        overnight_at = local_at(yesterday, 2, 0)
        db.add(LogEntry(
            property_id=hvh.id, author_user_id=staff["marcus"].id,
            department_id=depts["housekeeping"].id, shift=shift_for(hvh, overnight_at),
            body=("Guest in 219 reported a leak under the bathroom sink around 1:45am. "
                  "Engineering shut off the supply line; towels are down and the floor is wet. "
                  "Needs a full clean and dry-out before the room can be resold."),
            requires_ack=True,
            ack_expected=[staff["hana"].id, staff["rosa"].id, staff["hk_sup"].id],
            created_at=overnight_at))
        db.flush()

        # ---- content
        for shortcut, title, body, dept in data.QUICK_REPLIES:
            db.add(QuickReply(property_id=hvh.id, shortcut=shortcut, title=title, body=body,
                              department_id=depts[dept].id if dept else None,
                              usage_count=rng.randint(0, 220)))
        db.add(QuickReply(property_id=hvh.id, shortcut="/oldshuttle", title="Old shuttle",
                          body="Retired.", active=False))
        for name, typ, url, cat in data.ASSETS:
            db.add(DigitalAsset(property_id=hvh.id, name=name, type=AssetType(typ), url=url,
                                category=cat, short_code=new_short_code(db),
                                send_count=rng.randint(0, 80)))
        cats = {}
        for parent, children in data.CATEGORIES.items():
            p = ResolutionCategory(property_id=hvh.id, name=parent)
            db.add(p)
            db.flush()
            cats[parent] = p
            for c in children:
                db.add(ResolutionCategory(property_id=hvh.id, name=c, parent_id=p.id))
        db.flush()

        # ---- conversations (30) + work orders
        in_house = [s for s in stays
                   if s.property_id == hvh.id and s.status == StayStatus.checked_in]
        agents = [staff["ava"], staff["marcus"], staff["jordan"]]
        eng_staff = [staff["eli"], staff["noah"]]
        hk_staff = [staff["hana"], staff["rosa"]]
        convs: list[Conversation] = []
        work_orders: list[WorkOrder] = []

        def add_msg(c, direction, body, at, author=None, status=DeliveryStatus.delivered,
                    redacted=False, author_type=None):
            m = Message(conversation_id=c.id, property_id=c.property_id, direction=direction,
                        author_type=author_type or (AuthorType.guest
                                                    if direction == Direction.inbound
                                                    else AuthorType.staff),
                        author_user_id=author.id if author else None, channel=Channel.sms,
                        body=body, delivery_status=status,
                        provider_message_id=f"seed-{rng.randint(10**8, 10**9)}", redacted=redacted,
                        sent_at=at,
                        delivered_at=at if status == DeliveryStatus.delivered else None,
                        provider_error_code="30007" if status == DeliveryStatus.failed else None,
                        provider_error_message=("Carrier violation (mock)"
                                                if status == DeliveryStatus.failed else None))
            db.add(m)
            return m

        def add_wo(title, typ, prio, dept_type, status, conv=None, assignee=None, created=None):
            created = created or now - timedelta(minutes=rng.randint(10, 600))
            started_if = (WorkOrderStatus.in_progress, WorkOrderStatus.blocked,
                         WorkOrderStatus.complete)
            wo = WorkOrder(property_id=hvh.id, title=title, type=WorkOrderType(typ),
                           priority=Priority(prio), status=status,
                           location_ref=(conv.stay.room_number
                                        if conv and conv.stay else rng.choice(rooms)),
                           department_id=depts[dept_type].id,
                           assigned_user_id=assignee.id if assignee else None,
                           reported_by_user_id=rng.choice(agents).id,
                           source_conversation_id=conv.id if conv else None,
                           created_at=created, updated_at=created,
                           started_at=(created + timedelta(minutes=5)
                                      if status in started_if else None),
                           completed_at=(created + timedelta(minutes=rng.randint(10, 60))
                                        if status == WorkOrderStatus.complete else None))
            db.add(wo)
            db.flush()
            db.add(WorkOrderEvent(work_order_id=wo.id, property_id=hvh.id,
                                  user_id=wo.reported_by_user_id, type=WorkOrderEventType.created,
                                  to_value="open", created_at=created))
            work_orders.append(wo)
            return wo

        # 30 conversations incl. Tom's below: 7 fresh unassigned, 6 answered+assigned, 5 overdue,
        # 4 resolved-eligible, 5 archived, 2 with prompts (= 29) + Tom's failed-delivery
        # conversation.
        openers = list(data.GUEST_OPENERS)
        rng.shuffle(openers)
        plan = (["fresh"] * 7 + ["answered"] * 6 + ["overdue"] * 5 + ["resolved"] * 4
               + ["archived"] * 5 + ["prompt"] * 2)
        conv_stays = [s for s in in_house if s.room_number not in ("412", "516")]
        rng.shuffle(conv_stays)
        for i, kind in enumerate(plan):
            stay = conv_stays[i]
            guest = db.get(Guest, stay.guest_id)
            opener, dept_type, _neg = openers[i % len(openers)]
            c = Conversation(property_id=hvh.id, guest_id=guest.id, stay_id=stay.id,
                             status=ConversationStatus.open, channel_primary=Channel.sms)
            db.add(c)
            db.flush()
            c.stay = stay
            if kind == "fresh":
                at = now - timedelta(minutes=rng.randint(1, 12))
                add_msg(c, Direction.inbound, opener, at)
                c.last_guest_message_at = at
                c.sla_due_at = at + timedelta(minutes=15)
            elif kind == "answered":
                at = now - timedelta(minutes=rng.randint(20, 180))
                agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES),
                        at + timedelta(minutes=2), agent)
                c.last_guest_message_at = at
                c.last_staff_message_at = at + timedelta(minutes=2)
                c.first_response_seconds = 120
                c.assigned_user_id = agent.id
                # every answered conversation gets a linked WO (spec: 6 linked)
                dt = dept_type or "front_desk"
                pool_for = [w for w in data.WORK_ORDERS if w[3] == dt]
                assignees = (eng_staff if dt == "engineering"
                            else hk_staff if dt == "housekeeping" else agents)
                add_wo(rng.choice(pool_for)[0],
                       "maintenance" if dt == "engineering" else "guest_request",
                       "normal", dt, WorkOrderStatus.assigned, conv=c,
                       assignee=rng.choice(assignees))
            elif kind == "overdue":
                at = now - timedelta(minutes=rng.randint(20, 90))
                add_msg(c, Direction.inbound, opener, at)
                c.last_guest_message_at = at
                c.sla_due_at = at + timedelta(minutes=15)
                c.sla_breach_notified_at = at + timedelta(minutes=16)
                c.assigned_department_id = depts[dept_type or "front_desk"].id
            elif kind == "resolved":
                at = now - timedelta(hours=rng.randint(5, 20))
                agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES),
                        at + timedelta(minutes=4), agent)
                c.last_guest_message_at = at
                c.last_staff_message_at = at + timedelta(minutes=4)
                c.first_response_seconds = 240
            elif kind == "archived":
                at = now - timedelta(days=rng.randint(1, 3))
                agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES),
                        at + timedelta(minutes=3), agent)
                c.last_guest_message_at = at
                c.last_staff_message_at = at + timedelta(minutes=3)
                c.first_response_seconds = 180
                c.status = ConversationStatus.archived
                c.archived_at = at + timedelta(hours=5)
                c.resolution_category_id = rng.choice(list(cats.values())).id
            elif kind == "prompt":
                at = now - timedelta(minutes=rng.randint(30, 60))
                agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, data.STAFF_REPLIES[0], at + timedelta(minutes=3),
                        agent)
                c.last_guest_message_at = at
                c.last_staff_message_at = at + timedelta(minutes=3)
                c.first_response_seconds = 180
                c.assigned_user_id = agent.id
                wo = add_wo("AC not cooling" if i % 2 == 0 else "Shower drain slow", "maintenance",
                            "urgent", "engineering", WorkOrderStatus.complete, conv=c,
                            assignee=staff["eli"], created=at + timedelta(minutes=1))
                db.add(DraftPrompt(property_id=hvh.id, conversation_id=c.id, work_order_id=wo.id,
                                   status=DraftPromptStatus.pending,
                                   body=(f"Hi {guest.first_name} — our team has taken care of "
                                        f"\"{wo.title.lower()}\" in {stay.room_number}. Please "
                                        "text us if anything still isn't right.")))
            if i % 6 == 0:
                db.add(InternalNote(conversation_id=c.id, property_id=hvh.id,
                                    author_user_id=rng.choice(agents).id,
                                    body=rng.choice(data.NOTES), mentions=[]))
            convs.append(c)

        # Sarah's showcase conversation is one of the 30: make conversation 0 hers instead of a
        # random stay.
        # (Simplest: rewire conv[0].) Replace its guest/stay with Sarah's and give it the AC story.
        showcase = convs[0]
        sarah_stay = next(s for s in stays if s.guest_id == sarah.id)
        showcase.guest_id = sarah.id
        showcase.stay_id = sarah_stay.id
        showcase.stay = sarah_stay
        for m in db.scalars(select(Message).where(Message.conversation_id == showcase.id)).all():
            db.delete(m)
        db.flush()
        t0 = now - timedelta(minutes=23)
        add_msg(showcase, Direction.outbound,
                "Welcome to Harbourview, Sarah. You're in 412. WiFi: Harbourview-Guest, no "
                "password. Text us anytime.",
                t0 - timedelta(hours=3), author_type=AuthorType.automation)
        add_msg(showcase, Direction.inbound,
                "Hi, the AC in our room isn't working at all, it's really warm in here. We tried "
                "turning it off and on.", t0)
        add_msg(showcase, Direction.outbound,
                "So sorry about that, Sarah. I'm sending engineering up to 412 now — they'll knock "
                "in the next 15 minutes.",
                t0 + timedelta(minutes=3), staff["ava"])
        add_msg(showcase, Direction.inbound, "Thank you, someone just came by",
                t0 + timedelta(minutes=17))
        showcase.last_guest_message_at = t0 + timedelta(minutes=17)
        showcase.last_staff_message_at = t0 + timedelta(minutes=3)
        showcase.first_response_seconds = 180
        showcase.assigned_user_id = staff["ava"].id
        showcase.sla_due_at = t0 + timedelta(minutes=32)
        showcase.status = ConversationStatus.open
        showcase.archived_at = None
        db.add(InternalNote(conversation_id=showcase.id, property_id=hvh.id,
                            author_user_id=staff["ava"].id,
                            body=("Raised WO to Engineering, urgent. Sarah is Gold, 4th stay; "
                                 "if it's not fixed by 7:30 offer 518."), mentions=[]))

        # A failed outbound to Tom (…0000) and a redacted card message from another guest.
        tom_conv = Conversation(property_id=hvh.id, guest_id=tom.id,
                                stay_id=next(s.id for s in stays if s.guest_id == tom.id),
                                status=ConversationStatus.open, channel_primary=Channel.sms)
        db.add(tom_conv)
        db.flush()
        add_msg(tom_conv, Direction.inbound, "Is late checkout possible?",
                now - timedelta(minutes=50))
        add_msg(tom_conv, Direction.outbound, "Of course — extended to 1 PM.",
                now - timedelta(minutes=48), staff["marcus"], status=DeliveryStatus.failed)
        tom_conv.last_guest_message_at = now - timedelta(minutes=50)
        tom_conv.last_staff_message_at = now - timedelta(minutes=48)
        tom_conv.first_response_seconds = 120
        tom_conv.assigned_user_id = staff["marcus"].id
        # brief omitted this; without it summary.conversations undercounts by 1 (test expects 30)
        convs.append(tom_conv)
        card_conv = convs[3]
        add_msg(card_conv, Direction.inbound, "you can charge it to **** **** **** 4242",
                now - timedelta(minutes=5), redacted=True)

        # spec §8 calls for a conversation with no stay behind it, and there was none: a guest who
        # texts while not in-house. `room_number` is null on this one and quick-reply
        # interpolation has to fall back.
        diego = make_guest(hvh, "Diego", "Ruiz")
        nostay_conv = Conversation(property_id=hvh.id, guest_id=diego.id, stay_id=None,
                                   status=ConversationStatus.open, channel_primary=Channel.sms)
        db.add(nostay_conv)
        db.flush()
        at = now - timedelta(minutes=34)
        add_msg(nostay_conv, Direction.inbound,
                "Hi — I have a reservation for next Thursday. Is early check-in possible?", at)
        nostay_conv.last_guest_message_at = at
        nostay_conv.sla_due_at = at + timedelta(minutes=15)
        convs.append(nostay_conv)

        # ---- Lakeside Inn conversations. Property B had none at all, so switching property
        # landed on an empty inbox and made the switcher look broken.
        lsi_stays = [s for s in stays if s.property_id == lsi.id]
        for idx, (kind, minutes_ago) in enumerate((("fresh", 4), ("fresh", 26), ("answered", 95),
                                                   ("archived", 1700))):
            stay = lsi_stays[idx]
            opener = openers[(idx + 7) % len(openers)][0]
            c = Conversation(property_id=lsi.id, guest_id=stay.guest_id, stay_id=stay.id,
                             status=ConversationStatus.open, channel_primary=Channel.sms)
            db.add(c)
            db.flush()
            at = now - timedelta(minutes=minutes_ago)
            add_msg(c, Direction.inbound, opener, at)
            c.last_guest_message_at = at
            if kind == "fresh":
                c.sla_due_at = at + timedelta(minutes=15)
            else:
                add_msg(c, Direction.outbound, data.STAFF_REPLIES[1], at + timedelta(minutes=3),
                        bea)
                c.last_staff_message_at = at + timedelta(minutes=3)
                c.first_response_seconds = 180
                c.assigned_user_id = bea.id
                if kind == "archived":
                    c.status = ConversationStatus.archived
                    c.archived_at = at + timedelta(hours=2)
                    # No resolution category: every seeded category belongs to Harbourview, and
                    # pointing a Lakeside conversation at one would be a tenancy bug in the data.
            convs.append(c)
        db.flush()

        # Fill remaining open work orders to reach 15 active (not verified/cancelled).
        active_statuses = (WorkOrderStatus.open, WorkOrderStatus.assigned,
                          WorkOrderStatus.in_progress, WorkOrderStatus.blocked,
                          WorkOrderStatus.complete)
        active = [w for w in work_orders if w.status in active_statuses]
        pool = [w for w in data.WORK_ORDERS if w[0] not in {x.title for x in active}]
        statuses = [WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress,
                   WorkOrderStatus.blocked, WorkOrderStatus.open]
        j = 0
        while len(active) < 15:
            title, typ, prio, dept_type = pool[j % len(pool)]
            j += 1
            st = statuses[j % len(statuses)]
            assignee = (None if st == WorkOrderStatus.open
                       else rng.choice(eng_staff if dept_type == "engineering" else hk_staff))
            active.append(add_wo(title, typ, prio, dept_type, st, assignee=assignee))
        # A few closed ones for analytics history.
        for k in range(6):
            title, typ, prio, dept_type = data.WORK_ORDERS[k]
            add_wo(title, typ, prio, dept_type, WorkOrderStatus.verified,
                   assignee=rng.choice(eng_staff), created=now - timedelta(days=rng.randint(1, 6)))

        # ---- preventative maintenance (PM spec §9): the inventory, two sweep templates, one
        # scheduled template, and enough runs that every PM screen has something to show.
        units: dict[str, MaintainableUnit] = {}
        for row in unit_rows():
            u = MaintainableUnit(property_id=hvh.id, kind=PmUnitKind(row["kind"]),
                                 code=row["code"], name=row["name"], floor=row["floor"],
                                 room_type=row["room_type"], external_id=row["external_id"],
                                 source=PmUnitSource.manual)
            db.add(u)
            units[u.code] = u
        db.flush()

        def pm_template(name, mode, *, unit_kind=None, cadence=None, rrule=None, dtstart=None,
                        items=(), targets=()):
            t = PmTemplate(property_id=hvh.id, name=name, mode=mode,
                           department_id=depts["engineering"].id, unit_kind=unit_kind,
                           cadence=cadence, rrule=rrule, rrule_dtstart=dtstart,
                           last_fired_at=now if mode == PmTemplateMode.scheduled else None)
            db.add(t)
            db.flush()
            for position, (label, item_type, unit, lo, hi, required) in enumerate(items):
                db.add(PmTemplateItem(template_id=t.id, property_id=hvh.id, position=position,
                                      label=label, item_type=item_type, unit=unit,
                                      min_value=lo, max_value=hi, required=required))
            for code in targets:
                db.add(PmTemplateUnit(template_id=t.id, unit_id=units[code].id,
                                      property_id=hvh.id))
            db.flush()
            return t

        CB, NUM, TXT, PHOTO = (PmItemType.checkbox, PmItemType.number, PmItemType.text,
                               PmItemType.photo)
        rooms_t = pm_template(
            "Guest Room Quarterly", PmTemplateMode.sweep, unit_kind=PmUnitKind.guest_room,
            cadence=PmCadence.quarterly, items=[
                ("HVAC filter replaced", CB, None, None, None, True),
                ("Tap hot-water temperature", NUM, "°F", 100, 120, True),
                ("GFCI outlets tested", CB, None, None, None, True),
                ("Caulk and grout condition", TXT, None, None, None, False),
                ("Bathroom exhaust fan photo", PHOTO, None, None, None, True),
                ("Smoke detector tested", CB, None, None, None, True),
            ])
        areas_t = pm_template(
            "Common Areas Monthly", PmTemplateMode.sweep, unit_kind=PmUnitKind.common_area,
            cadence=PmCadence.monthly, items=[
                ("Lighting fully working", CB, None, None, None, True),
                ("Floor surfaces safe and clean", CB, None, None, None, True),
                ("Notes", TXT, None, None, None, False),
            ])
        local_today = pm_cycles.local_today(hvh, now)
        q_start, q_end, q_ord = pm_cycles.window_for(PmCadence.quarterly, local_today)
        boilers_t = pm_template(
            "Boiler inspection", PmTemplateMode.scheduled, rrule="FREQ=MONTHLY;INTERVAL=3",
            dtstart=q_start, targets=("BOILER-1", "BOILER-2"), items=[
                ("Operating pressure", NUM, "psi", 10, 30, True),
                ("Relief valve tested", CB, None, None, None, True),
                ("Burner flame photo", PHOTO, None, None, None, True),
                ("Notes", TXT, None, None, None, False),
            ])

        # Cycles: this quarter open, last quarter closed; this month open for common areas.
        p_start, p_end, p_ord = pm_cycles.window_for(PmCadence.quarterly,
                                                     q_start - timedelta(days=1))
        current_cycle = PmCycle(property_id=hvh.id, template_id=rooms_t.id, ordinal=q_ord,
                                starts_on=q_start, ends_on=q_end, status=PmCycleStatus.open)
        previous_cycle = PmCycle(property_id=hvh.id, template_id=rooms_t.id, ordinal=p_ord,
                                 starts_on=p_start, ends_on=p_end, status=PmCycleStatus.closed)
        m_start, m_end, m_ord = pm_cycles.window_for(PmCadence.monthly, local_today)
        db.add_all([current_cycle, previous_cycle,
                    PmCycle(property_id=hvh.id, template_id=areas_t.id, ordinal=m_ord,
                            starts_on=m_start, ends_on=m_end, status=PmCycleStatus.open)])
        db.flush()

        room_items = db.scalars(select(PmTemplateItem)
                                .where(PmTemplateItem.template_id == rooms_t.id)
                                .order_by(PmTemplateItem.position)).all()
        sam = staff["sam"]

        def seed_room_run(code, cycle, status, at, *, by=None, inspector=None, note=None):
            """A run with plausible answers. `at` is an aware UTC start time inside the cycle."""
            done = status in (PmRunStatus.completed, PmRunStatus.passed, PmRunStatus.failed)
            run = PmRun(property_id=hvh.id, template_id=rooms_t.id, unit_id=units[code].id,
                        cycle_id=cycle.id, status=status,
                        started_by_user_id=by.id if by else None, started_at=at if by else None,
                        completed_at=at + timedelta(minutes=35) if done else None,
                        inspected_by_user_id=inspector.id if inspector else None,
                        inspected_at=at + timedelta(hours=3) if inspector else None,
                        inspection_note=note, created_at=at, updated_at=at)
            db.add(run)
            db.flush()
            if status == PmRunStatus.missed:
                return run
            for item in room_items:
                a = PmRunAnswer(run_id=run.id, property_id=hvh.id, item_id=item.id)
                if done or rng.random() < 0.5:  # an in-progress run is part-way through
                    if item.item_type == PmItemType.checkbox:
                        a.bool_value = True
                    elif item.item_type == PmItemType.number:
                        a.number_value = float(rng.randint(104, 118))
                    elif item.item_type == PmItemType.text:
                        a.text_value = rng.choice(["Good", "Minor wear, monitored",
                                                   "Resealed tub edge"])
                    elif item.item_type == PmItemType.photo:
                        db.add(PmRunPhoto(run_id=run.id, property_id=hvh.id, item_id=item.id,
                                          uploaded_by_user_id=run.started_by_user_id,
                                          content_type="image/png", byte_size=len(TINY_PNG),
                                          data=TINY_PNG))
                    a.answered_at = at + timedelta(minutes=rng.randint(1, 30))
                db.add(a)
            db.flush()
            return run

        def within(cycle_start, cycle_end):
            """A start time on a random day of the window, never after `now`."""
            last = min(cycle_end, local_today)
            day = cycle_start + timedelta(days=rng.randint(0, max((last - cycle_start).days, 0)))
            at = pm_cycles.local_day_start_utc(hvh, day) + timedelta(hours=rng.randint(8, 16))
            return min(at, now - timedelta(minutes=45))

        room_codes = [c for c, u in units.items() if u.kind == PmUnitKind.guest_room]
        rng.shuffle(room_codes)
        # This quarter: 40 passed, 3 in progress, 4 awaiting inspection, 2 failed (= 49 runs).
        for code in room_codes[:40]:
            seed_room_run(code, current_cycle, PmRunStatus.passed, within(q_start, q_end),
                          by=rng.choice(eng_staff), inspector=sam)
        for code in room_codes[40:43]:
            seed_room_run(code, current_cycle, PmRunStatus.in_progress,
                          now - timedelta(minutes=rng.randint(5, 40)), by=rng.choice(eng_staff))
        for code in room_codes[43:47]:
            seed_room_run(code, current_cycle, PmRunStatus.completed, within(q_start, q_end),
                          by=rng.choice(eng_staff))
        for code, note in zip(room_codes[47:49], ("Fan grille still dusty in the photo.",
                                                  "Smoke detector ticked but not test-pressed."),
                             strict=True):
            seed_room_run(code, current_cycle, PmRunStatus.failed, within(q_start, q_end),
                          by=rng.choice(eng_staff), inspector=sam, note=note)
        # Last quarter, frozen: 110 passed, 10 missed.
        rng.shuffle(room_codes)
        for code in room_codes[:110]:
            seed_room_run(code, previous_cycle, PmRunStatus.passed, within(p_start, p_end),
                          by=rng.choice(eng_staff), inspector=sam)
        for code in room_codes[110:]:
            seed_room_run(code, previous_cycle, PmRunStatus.missed,
                          pm_cycles.local_day_start_utc(hvh, p_end + timedelta(days=1)))

        # The boiler schedule's occurrence at the start of this quarter: one pm work order and
        # one pending run per boiler, exactly what pm.tick would have written. last_fired_at is
        # `now`, so the tick will not write them again.
        due = pm_cycles.local_day_start_utc(hvh, q_start)
        for code in ("BOILER-1", "BOILER-2"):
            unit = units[code]
            wo = WorkOrder(property_id=hvh.id, title=f"Boiler inspection — {unit.name}",
                           type=WorkOrderType.pm, priority=Priority.normal,
                           status=WorkOrderStatus.open, location_type=LocationType.equipment,
                           location_ref=unit.code, department_id=depts["engineering"].id,
                           due_at=due, created_at=due, updated_at=due)
            db.add(wo)
            db.flush()
            db.add(WorkOrderEvent(work_order_id=wo.id, property_id=hvh.id, user_id=None,
                                  type=WorkOrderEventType.created, to_value="open",
                                  created_at=due))
            db.add(PmRun(property_id=hvh.id, template_id=boilers_t.id, unit_id=unit.id,
                         work_order_id=wo.id, status=PmRunStatus.pending, due_at=due,
                         created_at=due, updated_at=due))
        db.flush()

        # ---- housekeeping (spec §6). Through the domain, never around it: stage "last night",
        # run the real tick, then a mid-shift morning as the seeded users — so a broken
        # transition rule fails the seed loudly instead of seeding an impossible board. Last in
        # the file so the rng draws above it are unchanged.
        hk_rooms.ensure_rooms(db, hvh.id)
        last_night = datetime.combine(pm_cycles.local_today(hvh) - timedelta(days=1), time(18, 0),
                                      tzinfo=ZoneInfo(hvh.timezone))
        for room, _ in hk_rooms.active_rooms(db, hvh.id):
            room.status_changed_at = last_night
        db.flush()
        hk_tick.tick(db)  # dirties the stayovers and today's departures by the real rules

        grace, hana, rosa = staff["hk_sup"], staff["hana"], staff["rosa"]
        dirty = [r for r, _ in hk_rooms.active_rooms(db, hvh.id) if r.hk_status == HkStatus.dirty]
        rng.shuffle(dirty)
        by_keeper = {}
        for keeper, batch in ((hana, dirty[:14]), (rosa, dirty[14:28])):
            assigned = hk_assignments.assign(db, hvh.id, grace.id, [r.id for r in batch],
                                             keeper.id)
            by_keeper[keeper.id] = assigned
            # per housekeeper: 0-3 passed, 4-5 done, 6 in progress, 7 failed back, 8-13 assigned
            for i, a in enumerate(assigned[:8]):
                hk_transitions.start(db, hvh.id, keeper.id, Role.dept_staff, a.id)
                if i == 0:
                    hk_photos.attach(db, hvh.id, keeper.id, Role.dept_staff, a.id,
                                     data=TINY_PNG)
                if i == 6:
                    continue
                hk_transitions.complete(db, hvh.id, keeper.id, Role.dept_staff, a.id)
                if i <= 3:
                    hk_transitions.inspect(db, hvh.id, grace.id, a.id, "pass", None)
                elif i == 7:
                    hk_transitions.inspect(db, hvh.id, grace.id, a.id, "fail",
                                           "Hair in the bathroom sink.")
        waiting = by_keeper[rosa.id][8:]
        rush = next((a for a in waiting if a.type == HkServiceType.departure), waiting[0])
        hk_transitions.set_rush(db, hvh.id, staff["marcus"].id, rush.room_id, True)
        worked = {a.room_id for batch in by_keeper.values() for a in batch}
        vacant = [r for r, _ in hk_rooms.active_rooms(db, hvh.id)
                  if r.hk_status == HkStatus.inspected and r.id not in worked][:3]
        for room, status, note in ((vacant[0], HkStatus.out_of_order, "AC unit leaking, WO open"),
                                   (vacant[1], HkStatus.out_of_order, "AC unit leaking, WO open"),
                                   (vacant[2], HkStatus.out_of_service, "Carpet replacement")):
            hk_transitions.set_room_status(db, hvh.id, grace.id, room.id, status, note)
        db.flush()

        # ---- recurring jobs
        for job_type in ("sla.sweep", "snooze.wake", "pms.tick", "pm.tick", "housekeeping.tick"):
            jobs.ensure_recurring(db, job_type)

        # Derive every count from the database rather than in-memory counters/lists: the showcase
        # rewire above deletes and re-adds messages, which desynced a running `messages` counter
        # (found in review — SeedSummary.messages reported 53 while the actual row count was 52).
        # Querying the real rows after all mutations means no future rewire can desync this again.
        summary = SeedSummary(
            properties=db.scalar(select(func.count()).select_from(Property)),
            users=db.scalar(select(func.count()).select_from(UserAccount)),
            guests=db.scalar(select(func.count()).select_from(Guest)),
            stays=db.scalar(select(func.count()).select_from(Stay)),
            conversations=db.scalar(select(func.count()).select_from(Conversation)),
            messages=db.scalar(select(func.count()).select_from(Message)),
            work_orders=db.scalar(select(func.count()).select_from(WorkOrder)),
            log_entries=db.scalar(select(func.count()).select_from(LogEntry)),
            maintainable_units=db.scalar(select(func.count()).select_from(MaintainableUnit)),
            pm_templates=db.scalar(select(func.count()).select_from(PmTemplate)),
            pm_runs=db.scalar(select(func.count()).select_from(PmRun)),
            rooms=db.scalar(select(func.count()).select_from(Room)),
            hk_assignments=db.scalar(select(func.count()).select_from(HousekeepingAssignment)),
        )
    database.engine.dispose()
    return summary


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    url = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
    # reset deletes the sqlite FILE, which means nothing for any other backend — and run()
    # refuses it there rather than seeding on top of a database it cannot safely clear.
    print(run(url, reset=url.startswith("sqlite:///")))
