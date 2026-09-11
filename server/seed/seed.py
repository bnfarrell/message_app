"""Deterministic development seed. `flask seed` or `python -m seed.seed`. Matches spec §8.

Determinism covers the shape and content of the seeded data (names, counts, message bodies, phone
numbers, timing, etc.) — all driven from `random.Random(42)`, so two runs produce identical data
(ids aside, since those are `uuid.uuid4()`). It deliberately does NOT cover `DigitalAsset.short_code`:
those come from `app.domain.assets.new_short_code`, which uses `secrets.choice`, not this module's
seeded RNG, because a short code is the public, guest-facing `/a/<code>` URL sent over SMS — making it
predictable to satisfy a determinism goal would be a real security regression. Short codes differ
between seed runs; everything else does not.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from app import clock
from app.auth.passwords import hash_password
from app.db import Database, run_migrations
from app.domain.assets import new_short_code
from app.models import (Conversation, Department, DigitalAsset, DraftPrompt, Guest, InternalNote, Message, Property,
                        PropertyMembership, QuickReply, ResolutionCategory, Stay, UserAccount, WorkOrder,
                        WorkOrderEvent)
from app.queue import jobs
from app.schemas.enums import (AssetType, AuthorType, Channel, ConversationStatus, DeliveryStatus, DepartmentType,
                               Direction, DraftPromptStatus, Priority, Role, SmsConsentStatus, StayStatus,
                               WorkOrderEventType, WorkOrderStatus, WorkOrderType)
from seed import data

PASSWORD = "Password123!"


@dataclass
class SeedSummary:
    properties: int
    users: int
    guests: int
    stays: int
    conversations: int
    messages: int
    work_orders: int


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
        hvh = Property(name="Harbourview Hotel", code="HVH", timezone="America/New_York", sms_number="+15550100",
                       address="1 Harbour St", currency="USD", primary_color="#f0b323",
                       settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                                 "help_text": "Harbourview Hotel: text us anytime, or call +1 555 0100."})
        lsi = Property(name="Lakeside Inn", code="LSI", timezone="America/Chicago", sms_number="+15550200",
                       settings={"sla_minutes": 15, "auto_resolve_hours": 4, "help_text": "Lakeside Inn: call +1 555 0200."})
        db.add_all([hvh, lsi]); db.flush()
        depts = {}
        for name, typ in [("Front Desk", DepartmentType.front_desk), ("Housekeeping", DepartmentType.housekeeping),
                          ("Engineering", DepartmentType.engineering)]:
            d = Department(property_id=hvh.id, name=name, type=typ); db.add(d); depts[typ.value] = d
        lsi_fd = Department(property_id=lsi.id, name="Front Desk", type=DepartmentType.front_desk); db.add(lsi_fd)
        db.flush()

        # ---- staff (12 at HVH + 2 at LSI)
        pw = hash_password(PASSWORD, rounds=10)

        def user(email, first, last):
            u = UserAccount(email=email, first_name=first, last_name=last, password_hash=pw); db.add(u); db.flush(); return u

        def member(u, prop, role, dept=None):
            db.add(PropertyMembership(user_id=u.id, property_id=prop.id, role=role, department_id=dept.id if dept else None))

        staff = {
            "ava": user("ava@hvh.test", "Ava", "Agent"), "marcus": user("marcus@hvh.test", "Marcus", "Reyes"),
            "jordan": user("jordan@hvh.test", "Jordan", "Tate"), "hana": user("hana@hvh.test", "Hana", "Keeper"),
            "rosa": user("rosa@hvh.test", "Rosa", "Lima"), "eli": user("eli@hvh.test", "Eli", "Engineer"),
            "noah": user("noah@hvh.test", "Noah", "Fix"), "hk_sup": user("hk.supervisor@hvh.test", "Grace", "Osei"),
            "sam": user("sam@hvh.test", "Sam", "Super"), "morgan": user("morgan@hvh.test", "Morgan", "Manager"),
            "alex": user("alex@hvh.test", "Alex", "Admin"), "casey": user("casey@group.test", "Casey", "Corp"),
        }
        member(staff["ava"], hvh, Role.agent, depts["front_desk"]); member(staff["marcus"], hvh, Role.agent, depts["front_desk"])
        member(staff["jordan"], hvh, Role.agent, depts["front_desk"])
        member(staff["hana"], hvh, Role.dept_staff, depts["housekeeping"]); member(staff["rosa"], hvh, Role.dept_staff, depts["housekeeping"])
        member(staff["eli"], hvh, Role.dept_staff, depts["engineering"]); member(staff["noah"], hvh, Role.dept_staff, depts["engineering"])
        member(staff["hk_sup"], hvh, Role.supervisor, depts["housekeeping"]); member(staff["sam"], hvh, Role.supervisor, depts["engineering"])
        member(staff["morgan"], hvh, Role.manager); member(staff["alex"], hvh, Role.admin); member(staff["casey"], hvh, Role.corporate)
        blake = user("blake@lsi.test", "Blake", "Admin"); member(blake, lsi, Role.admin)
        bea = user("bea@lsi.test", "Bea", "Agent"); member(bea, lsi, Role.agent, lsi_fd)
        member(staff["casey"], lsi, Role.corporate)

        # ---- rooms, guests, stays
        rooms = [f"{f}{n:02d}" for f in range(1, 7) for n in range(1, 21)]
        rng.shuffle(rooms)
        guests: list[Guest] = []
        stays: list[Stay] = []

        def make_guest(prop, first=None, last=None, phone=None, tier=None, consent=SmsConsentStatus.opted_in):
            g = Guest(property_id=prop.id, first_name=first or rng.choice(data.FIRST_NAMES),
                      last_name=last or rng.choice(data.LAST_NAMES), phone_e164=phone or _phone(rng, used_phones),
                      loyalty_tier=tier if tier is not None else rng.choice(data.LOYALTY),
                      vip=rng.random() < 0.05, sms_consent_status=consent,
                      sms_consent_at=now - timedelta(days=rng.randint(1, 400)), sms_consent_source="pms")
            db.add(g); db.flush(); guests.append(g); return g

        def make_stay(g, room, status, arrival, nights, res_id=None):
            s = Stay(guest_id=g.id, property_id=g.property_id, pms_reservation_id=res_id or f"RES-{room}-{rng.randint(1000, 9999)}",
                     room_number=room, room_type=rng.choice(data.ROOM_TYPES), rate_code=rng.choice(data.RATE_CODES),
                     status=status, arrival_date=arrival, departure_date=arrival + timedelta(days=nights),
                     adults=rng.choice([1, 2, 2, 2, 3]), children=rng.choice([0, 0, 0, 1, 2]),
                     is_return_guest=rng.random() < 0.3, stay_count=rng.randint(1, 6),
                     actual_checkin_at=(datetime.combine(arrival, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15))
                     if status != StayStatus.reserved else None,
                     actual_checkout_at=now - timedelta(hours=rng.randint(20, 40)) if status == StayStatus.checked_out else None,
                     raw_pms={"seed": True})
            db.add(s); db.flush(); stays.append(s); return s

        sarah = make_guest(hvh, "Sarah", "Chen", "+15551234567", "Gold")
        make_stay(sarah, "412", StayStatus.checked_in, today - timedelta(days=1), 3, res_id="RES-412")
        tom = make_guest(hvh, "Tom", "Becker", "+15552000000", "Silver")  # fails delivery on purpose
        make_stay(tom, "516", StayStatus.checked_in, today, 2)
        room_iter = iter(r for r in rooms if r not in ("412", "516"))
        for _ in range(83):
            g = make_guest(hvh); make_stay(g, next(room_iter), StayStatus.checked_in, today - timedelta(days=rng.randint(0, 4)), rng.randint(1, 5))
        for _ in range(10):
            g = make_guest(hvh); make_stay(g, next(room_iter), StayStatus.reserved, today, rng.randint(1, 4))
        departing = [s for s in stays if s.status == StayStatus.checked_in][2:12]
        for s in departing:
            s.departure_date = today
        for _ in range(7):  # + Lena below = 8 checked out
            g = make_guest(hvh); make_stay(g, rng.choice(rooms), StayStatus.checked_out, today - timedelta(days=3), 2)
        lena = make_guest(hvh, "Lena", "Park", "+15553104411", None, SmsConsentStatus.opted_out)
        lena.sms_consent_source = "sms_keyword"
        make_stay(lena, "301", StayStatus.checked_out, today - timedelta(days=4), 2)
        for _ in range(3):
            g = make_guest(lsi); make_stay(g, str(rng.randint(101, 140)), StayStatus.checked_in, today, 2)

        # ---- content
        for shortcut, title, body, dept in data.QUICK_REPLIES:
            db.add(QuickReply(property_id=hvh.id, shortcut=shortcut, title=title, body=body,
                              department_id=depts[dept].id if dept else None, usage_count=rng.randint(0, 220)))
        db.add(QuickReply(property_id=hvh.id, shortcut="/oldshuttle", title="Old shuttle", body="Retired.", active=False))
        for name, typ, url, cat in data.ASSETS:
            db.add(DigitalAsset(property_id=hvh.id, name=name, type=AssetType(typ), url=url, category=cat,
                                short_code=new_short_code(db), send_count=rng.randint(0, 80)))
        cats = {}
        for parent, children in data.CATEGORIES.items():
            p = ResolutionCategory(property_id=hvh.id, name=parent); db.add(p); db.flush(); cats[parent] = p
            for c in children:
                db.add(ResolutionCategory(property_id=hvh.id, name=c, parent_id=p.id))
        db.flush()

        # ---- conversations (30) + work orders
        in_house = [s for s in stays if s.property_id == hvh.id and s.status == StayStatus.checked_in]
        agents = [staff["ava"], staff["marcus"], staff["jordan"]]
        eng_staff = [staff["eli"], staff["noah"]]
        hk_staff = [staff["hana"], staff["rosa"]]
        convs: list[Conversation] = []
        work_orders: list[WorkOrder] = []

        def add_msg(c, direction, body, at, author=None, status=DeliveryStatus.delivered, redacted=False, author_type=None):
            m = Message(conversation_id=c.id, property_id=c.property_id, direction=direction,
                        author_type=author_type or (AuthorType.guest if direction == Direction.inbound else AuthorType.staff),
                        author_user_id=author.id if author else None, channel=Channel.sms, body=body, delivery_status=status,
                        provider_message_id=f"seed-{rng.randint(10**8, 10**9)}", redacted=redacted, sent_at=at,
                        delivered_at=at if status == DeliveryStatus.delivered else None,
                        provider_error_code="30007" if status == DeliveryStatus.failed else None,
                        provider_error_message="Carrier violation (mock)" if status == DeliveryStatus.failed else None)
            db.add(m); return m

        def add_wo(title, typ, prio, dept_type, status, conv=None, assignee=None, created=None):
            created = created or now - timedelta(minutes=rng.randint(10, 600))
            wo = WorkOrder(property_id=hvh.id, title=title, type=WorkOrderType(typ), priority=Priority(prio), status=status,
                           location_ref=(conv.stay.room_number if conv and conv.stay else rng.choice(rooms)),
                           department_id=depts[dept_type].id, assigned_user_id=assignee.id if assignee else None,
                           reported_by_user_id=rng.choice(agents).id, source_conversation_id=conv.id if conv else None,
                           created_at=created, updated_at=created,
                           started_at=created + timedelta(minutes=5) if status in (WorkOrderStatus.in_progress, WorkOrderStatus.blocked, WorkOrderStatus.complete) else None,
                           completed_at=created + timedelta(minutes=rng.randint(10, 60)) if status == WorkOrderStatus.complete else None)
            db.add(wo); db.flush()
            db.add(WorkOrderEvent(work_order_id=wo.id, property_id=hvh.id, user_id=wo.reported_by_user_id,
                                  type=WorkOrderEventType.created, to_value="open", created_at=created))
            work_orders.append(wo); return wo

        # 30 conversations incl. Tom's below: 7 fresh unassigned, 6 answered+assigned, 5 overdue,
        # 4 resolved-eligible, 5 archived, 2 with prompts (= 29) + Tom's failed-delivery conversation.
        openers = list(data.GUEST_OPENERS); rng.shuffle(openers)
        plan = (["fresh"] * 7 + ["answered"] * 6 + ["overdue"] * 5 + ["resolved"] * 4 + ["archived"] * 5 + ["prompt"] * 2)
        conv_stays = [s for s in in_house if s.room_number not in ("412", "516")]
        rng.shuffle(conv_stays)
        for i, kind in enumerate(plan):
            stay = conv_stays[i]
            guest = db.get(Guest, stay.guest_id)
            opener, dept_type, _neg = openers[i % len(openers)]
            c = Conversation(property_id=hvh.id, guest_id=guest.id, stay_id=stay.id, status=ConversationStatus.open,
                             channel_primary=Channel.sms)
            db.add(c); db.flush(); c.stay = stay
            if kind == "fresh":
                at = now - timedelta(minutes=rng.randint(1, 12))
                add_msg(c, Direction.inbound, opener, at)
                c.last_guest_message_at = at; c.sla_due_at = at + timedelta(minutes=15)
            elif kind == "answered":
                at = now - timedelta(minutes=rng.randint(20, 180)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES), at + timedelta(minutes=2), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=2)
                c.first_response_seconds = 120; c.assigned_user_id = agent.id
                dt = dept_type or "front_desk"  # every answered conversation gets a linked WO (spec: 6 linked)
                pool_for = [w for w in data.WORK_ORDERS if w[3] == dt]
                add_wo(rng.choice(pool_for)[0], "maintenance" if dt == "engineering" else "guest_request",
                       "normal", dt, WorkOrderStatus.assigned, conv=c,
                       assignee=rng.choice(eng_staff if dt == "engineering" else hk_staff if dt == "housekeeping" else agents))
            elif kind == "overdue":
                at = now - timedelta(minutes=rng.randint(20, 90))
                add_msg(c, Direction.inbound, opener, at)
                c.last_guest_message_at = at; c.sla_due_at = at + timedelta(minutes=15); c.sla_breach_notified_at = at + timedelta(minutes=16)
                c.assigned_department_id = depts[dept_type or "front_desk"].id
            elif kind == "resolved":
                at = now - timedelta(hours=rng.randint(5, 20)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES), at + timedelta(minutes=4), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=4); c.first_response_seconds = 240
            elif kind == "archived":
                at = now - timedelta(days=rng.randint(1, 3)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES), at + timedelta(minutes=3), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=3); c.first_response_seconds = 180
                c.status = ConversationStatus.archived; c.archived_at = at + timedelta(hours=5)
                c.resolution_category_id = rng.choice(list(cats.values())).id
            elif kind == "prompt":
                at = now - timedelta(minutes=rng.randint(30, 60)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, data.STAFF_REPLIES[0], at + timedelta(minutes=3), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=3); c.first_response_seconds = 180
                c.assigned_user_id = agent.id
                wo = add_wo("AC not cooling" if i % 2 == 0 else "Shower drain slow", "maintenance", "urgent", "engineering",
                            WorkOrderStatus.complete, conv=c, assignee=staff["eli"], created=at + timedelta(minutes=1))
                db.add(DraftPrompt(property_id=hvh.id, conversation_id=c.id, work_order_id=wo.id, status=DraftPromptStatus.pending,
                                   body=f"Hi {guest.first_name} — our team has taken care of \"{wo.title.lower()}\" in {stay.room_number}. Please text us if anything still isn't right."))
            if i % 6 == 0:
                db.add(InternalNote(conversation_id=c.id, property_id=hvh.id, author_user_id=rng.choice(agents).id,
                                    body=rng.choice(data.NOTES), mentions=[]))
            convs.append(c)

        # Sarah's showcase conversation is one of the 30: make conversation 0 hers instead of a random stay.
        # (Simplest: rewire conv[0].) Replace its guest/stay with Sarah's and give it the AC story.
        showcase = convs[0]
        sarah_stay = next(s for s in stays if s.guest_id == sarah.id)
        showcase.guest_id = sarah.id; showcase.stay_id = sarah_stay.id; showcase.stay = sarah_stay
        for m in db.scalars(select(Message).where(Message.conversation_id == showcase.id)).all():
            db.delete(m)
        db.flush()
        t0 = now - timedelta(minutes=23)
        add_msg(showcase, Direction.outbound, "Welcome to Harbourview, Sarah. You're in 412. WiFi: Harbourview-Guest, no password. Text us anytime.",
                t0 - timedelta(hours=3), author_type=AuthorType.automation)
        add_msg(showcase, Direction.inbound, "Hi, the AC in our room isn't working at all, it's really warm in here. We tried turning it off and on.", t0)
        add_msg(showcase, Direction.outbound, "So sorry about that, Sarah. I'm sending engineering up to 412 now — they'll knock in the next 15 minutes.",
                t0 + timedelta(minutes=3), staff["ava"])
        add_msg(showcase, Direction.inbound, "Thank you, someone just came by", t0 + timedelta(minutes=17))
        showcase.last_guest_message_at = t0 + timedelta(minutes=17); showcase.last_staff_message_at = t0 + timedelta(minutes=3)
        showcase.first_response_seconds = 180; showcase.assigned_user_id = staff["ava"].id
        showcase.sla_due_at = t0 + timedelta(minutes=32); showcase.status = ConversationStatus.open; showcase.archived_at = None
        db.add(InternalNote(conversation_id=showcase.id, property_id=hvh.id, author_user_id=staff["ava"].id,
                            body="Raised WO to Engineering, urgent. Sarah is Gold, 4th stay; if it's not fixed by 7:30 offer 518.", mentions=[]))

        # A failed outbound to Tom (…0000) and a redacted card message from another guest.
        tom_conv = Conversation(property_id=hvh.id, guest_id=tom.id, stay_id=next(s.id for s in stays if s.guest_id == tom.id),
                                status=ConversationStatus.open, channel_primary=Channel.sms)
        db.add(tom_conv); db.flush()
        add_msg(tom_conv, Direction.inbound, "Is late checkout possible?", now - timedelta(minutes=50))
        add_msg(tom_conv, Direction.outbound, "Of course — extended to 1 PM.", now - timedelta(minutes=48), staff["marcus"], status=DeliveryStatus.failed)
        tom_conv.last_guest_message_at = now - timedelta(minutes=50); tom_conv.last_staff_message_at = now - timedelta(minutes=48)
        tom_conv.first_response_seconds = 120; tom_conv.assigned_user_id = staff["marcus"].id
        convs.append(tom_conv)  # brief omitted this; without it summary.conversations undercounts by 1 (test expects 30)
        card_conv = convs[3]
        add_msg(card_conv, Direction.inbound, "you can charge it to **** **** **** 4242", now - timedelta(minutes=5), redacted=True)
        db.flush()

        # Fill remaining open work orders to reach 15 active (not verified/cancelled).
        active = [w for w in work_orders if w.status in (WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress,
                                                            WorkOrderStatus.blocked, WorkOrderStatus.complete)]
        pool = [w for w in data.WORK_ORDERS if w[0] not in {x.title for x in active}]
        statuses = [WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress, WorkOrderStatus.blocked, WorkOrderStatus.open]
        j = 0
        while len(active) < 15:
            title, typ, prio, dept_type = pool[j % len(pool)]; j += 1
            st = statuses[j % len(statuses)]
            assignee = None if st == WorkOrderStatus.open else rng.choice(eng_staff if dept_type == "engineering" else hk_staff)
            active.append(add_wo(title, typ, prio, dept_type, st, assignee=assignee))
        # A few closed ones for analytics history.
        for k in range(6):
            title, typ, prio, dept_type = data.WORK_ORDERS[k]
            add_wo(title, typ, prio, dept_type, WorkOrderStatus.verified, assignee=rng.choice(eng_staff), created=now - timedelta(days=rng.randint(1, 6)))

        # ---- recurring jobs
        for job_type in ("sla.sweep", "snooze.wake", "pms.tick"):
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
        )
    database.engine.dispose()
    return summary


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    print(run(os.getenv("DATABASE_URL", "sqlite:///data/app.db")))
