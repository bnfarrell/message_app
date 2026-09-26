"""Housekeeper photos (spec §2.4): bytes in the table, same cap and sniffing as work orders."""
import pytest

from app.domain import hk_assignments, hk_photos, hk_transitions
from app.domain.work_orders import MAX_PHOTO_BYTES
from app.errors import Forbidden, NotFound, TransitionError, ValidationFailed
from app.schemas.enums import Role
from tests.hk_helpers import make_rooms

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"
GIF = b"GIF89a" + b"\x00" * 40


def _assignment(db, fx, start=True):
    room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
    hk_transitions.mark_dirty(db, fx.property_a.id, fx.supervisor_a.id, room.id, None)
    (a,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                 fx.housekeeper_a.id)
    if start:
        hk_transitions.start(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff, a.id)
    return a


def test_attach_stores_the_bytes_while_in_progress(database, fx):
    with database.session() as db:
        a = _assignment(db, fx)
        photo = hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                                 a.id, data=PNG)
        assert (photo.content_type, photo.byte_size) == ("image/png", len(PNG))
        assert hk_photos.get_photo(db, fx.property_a.id, a.id, photo.id).data == PNG
        assert hk_photos.photos_for(db, [a.id])[a.id] == [photo]


def test_attach_refuses_bad_input_without_a_500(database, fx):
    with database.session() as db:
        a = _assignment(db, fx)
        for data in (b"", GIF, PNG + b"\x00" * MAX_PHOTO_BYTES):
            with pytest.raises(ValidationFailed):
                hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                                 a.id, data=data)
        with pytest.raises(Forbidden):
            hk_photos.attach(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, a.id,
                             data=PNG)


def test_photos_only_while_the_room_is_being_cleaned(database, fx):
    with database.session() as db:
        a = _assignment(db, fx, start=False)
        with pytest.raises(TransitionError):
            hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff, a.id,
                             data=PNG)


def test_get_photo_is_scoped_by_property_and_assignment(database, fx):
    with database.session() as db:
        a = _assignment(db, fx)
        photo = hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                                 a.id, data=PNG)
        with pytest.raises(NotFound):
            hk_photos.get_photo(db, fx.property_b.id, a.id, photo.id)
