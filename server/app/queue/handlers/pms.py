from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Property
from app.pms.handle_event import handle_event
from app.pms.mock_pms import MockPmsAdapter
from app.queue.handlers import handler

adapter = MockPmsAdapter()


@handler("pms.tick")
def pms_tick(db: Session, payload: dict) -> None:
    for pid in db.scalars(select(Property.id)).all():
        for event in adapter.next_events(db, pid):
            handle_event(db, event, integration_key=adapter.integration_key)
