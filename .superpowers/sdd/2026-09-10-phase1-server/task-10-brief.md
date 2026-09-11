### Task 10: Guests, stays, and consent

**Files:**
- Create: `server/app/domain/guests.py`, `server/app/domain/stays.py`, `server/app/domain/consent.py`, `server/tests/test_consent.py`, `server/tests/test_guests_stays.py`

**Interfaces:**
- Produces: `guests.find_by_phone(db, property_id, phone) -> Guest | None`; `guests.find_or_create_by_phone(db, property_id, phone) -> tuple[Guest, bool]` (created flag); `guests.normalize_phone(raw) -> str` (E.164 for US numbers: digits only → `+1XXXXXXXXXX`; already `+` → kept); `stays.find_in_house_for_guest(db, property_id, guest_id) -> Stay | None`; `stays.find_in_house_by_phone(db, property_id, phone) -> tuple[Guest, Stay] | None`; `consent.STOP_WORDS`, `consent.START_WORDS`, `consent.HELP_WORDS`; `consent.classify_keyword(body) -> Literal["stop","start","help"] | None`; `consent.opt_out(db, guest, source)`, `consent.opt_in(db, guest, source)`; `consent.assert_can_send(guest, *, allow_opt_out_confirmation=False)` raising `ConsentError`; `consent.STOP_CONFIRMATION(property_name) -> str`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_consent.py`:
```python
import pytest

from app.domain import consent
from app.errors import ConsentError
from app.models import Guest
from app.schemas.enums import SmsConsentStatus


@pytest.mark.parametrize("body,expected", [
    ("STOP", "stop"), ("stop", "stop"), (" Stop please ", "stop"), ("STOPALL", "stop"),
    ("UNSUBSCRIBE", "stop"), ("CANCEL", "stop"), ("END", "stop"), ("QUIT", "stop"),
    ("START", "start"), ("UNSTOP", "start"), ("YES", "start"),
    ("HELP", "help"), ("help me", "help"),
    ("Please stop the AC noise", None),     # 'stop' not the first word → real message
    ("Can you help with towels?", None),
    ("", None),
])
def test_classify_keyword(body, expected):
    assert consent.classify_keyword(body) == expected


def test_opt_out_and_opt_in_record_source_and_time(app, fx, database):
    from app import clock

    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        consent.opt_out(db, g, "sms_keyword")
        assert g.sms_consent_status == SmsConsentStatus.opted_out
        assert g.sms_consent_source == "sms_keyword"
        assert g.sms_consent_at == clock.now()
        consent.opt_in(db, g, "sms_keyword")
        assert g.sms_consent_status == SmsConsentStatus.opted_in


def test_assert_can_send_blocks_opted_out_unless_confirmation(app, fx, database):
    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        consent.assert_can_send(g)
        consent.opt_out(db, g, "sms_keyword")
        with pytest.raises(ConsentError) as ei:
            consent.assert_can_send(g)
        assert ei.value.code == "CONSENT_OPTED_OUT"
        consent.assert_can_send(g, allow_opt_out_confirmation=True)  # the one exception
```

`server/tests/test_guests_stays.py`:
```python
from app.domain import guests, stays
from app.schemas.enums import SmsConsentStatus


def test_normalize_phone():
    assert guests.normalize_phone("(555) 123-4567") == "+15551234567"
    assert guests.normalize_phone("15551234567") == "+15551234567"
    assert guests.normalize_phone("+44 20 7946 0958") == "+442079460958"


def test_find_or_create_by_phone_is_idempotent_and_property_scoped(app, fx, database):
    with database.session() as db:
        g1, created1 = guests.find_or_create_by_phone(db, fx.property_a.id, "+15550001111")
        g2, created2 = guests.find_or_create_by_phone(db, fx.property_a.id, "+1 (555) 000-1111")
        gb, createdb = guests.find_or_create_by_phone(db, fx.property_b.id, "+15550001111")
    assert created1 and not created2 and createdb
    assert g1.id == g2.id and gb.id != g1.id
    assert g1.sms_consent_status == SmsConsentStatus.unknown


def test_find_in_house_by_phone_matches_checked_in_stay_only(app, fx, database):
    with database.session() as db:
        hit = stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_inhouse_a.phone_e164)
        assert hit is not None and hit[1].room_number == "412"
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_nostay_a.phone_e164) is None
        # Same phone at another property is not in-house here.
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_b.phone_e164) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_consent.py tests/test_guests_stays.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `app/domain/guests.py`**

```python
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Guest


def normalize_phone(raw: str) -> str:
    raw = raw.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def find_by_phone(db: Session, property_id: str, phone: str) -> Guest | None:
    return db.scalar(select(Guest).where(Guest.property_id == property_id,
                                         Guest.phone_e164 == normalize_phone(phone)))


def find_or_create_by_phone(db: Session, property_id: str, phone: str) -> tuple[Guest, bool]:
    existing = find_by_phone(db, property_id, phone)
    if existing:
        return existing, False
    g = Guest(property_id=property_id, phone_e164=normalize_phone(phone))
    db.add(g)
    db.flush()
    return g, True


def get(db: Session, property_id: str, guest_id: str) -> Guest | None:
    return db.scalar(select(Guest).where(Guest.id == guest_id, Guest.property_id == property_id))
```

- [ ] **Step 4: Write `app/domain/stays.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.guests import find_by_phone
from app.models import Guest, Stay
from app.schemas.enums import StayStatus


def find_in_house_for_guest(db: Session, property_id: str, guest_id: str) -> Stay | None:
    return db.scalar(
        select(Stay).where(Stay.property_id == property_id, Stay.guest_id == guest_id,
                           Stay.status == StayStatus.checked_in)
        .order_by(Stay.actual_checkin_at.desc())
    )


def find_in_house_by_phone(db: Session, property_id: str, phone: str) -> tuple[Guest, Stay] | None:
    guest = find_by_phone(db, property_id, phone)
    if guest is None:
        return None
    stay = find_in_house_for_guest(db, property_id, guest.id)
    return (guest, stay) if stay else None


def get(db: Session, property_id: str, stay_id: str) -> Stay | None:
    return db.scalar(select(Stay).where(Stay.id == stay_id, Stay.property_id == property_id))
```

- [ ] **Step 5: Write `app/domain/consent.py`**

```python
"""TCPA consent (design.md §9.1). assert_can_send() is called from exactly one place: messages.send()."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app import clock
from app.domain import audit
from app.errors import ConsentError
from app.models import Guest
from app.schemas.enums import SmsConsentStatus

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
START_WORDS = {"start", "unstop", "yes"}
HELP_WORDS = {"help"}

Keyword = Literal["stop", "start", "help"]


def classify_keyword(body: str) -> Keyword | None:
    words = body.strip().lower().split()
    if not words:
        return None
    first = words[0].strip(".,!?")
    if first in STOP_WORDS:
        return "stop"
    if first in START_WORDS:
        return "start"
    if first in HELP_WORDS:
        return "help"
    return None


def STOP_CONFIRMATION(property_name: str) -> str:
    return f"You're unsubscribed from {property_name} messages. Reply START to resume."


def _set(db: Session, guest: Guest, status: SmsConsentStatus, source: str) -> None:
    before = {"sms_consent_status": guest.sms_consent_status.value}
    guest.sms_consent_status = status
    guest.sms_consent_at = clock.now()
    guest.sms_consent_source = source
    db.flush()
    audit.record(db, guest.property_id, None, f"consent.{status.value}", "guest", guest.id,
                 before=before, after={"sms_consent_status": status.value, "source": source})


def opt_out(db: Session, guest: Guest, source: str) -> None:
    _set(db, guest, SmsConsentStatus.opted_out, source)


def opt_in(db: Session, guest: Guest, source: str) -> None:
    _set(db, guest, SmsConsentStatus.opted_in, source)


def assert_can_send(guest: Guest, *, allow_opt_out_confirmation: bool = False) -> None:
    if guest.sms_consent_status == SmsConsentStatus.opted_out and not allow_opt_out_confirmation:
        raise ConsentError("Guest has opted out of SMS")
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): guests, in-house stay lookup, TCPA consent keywords and send-path check"
```

---

