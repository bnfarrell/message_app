"""Housekeeper photos (spec §2.4). Bytes in the table with `data` deferred, exactly as
work_order_photo and pm_run_photo, because the deployment filesystem is ephemeral."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, hk_assignments, hk_rooms, hk_transitions
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import NotFound, TransitionError, ValidationFailed
from app.models import HousekeepingPhoto
from app.schemas.enums import HkAssignmentStatus, Role


def attach(db: Session, property_id: str, actor_id: str, role: Role, assignment_id: str, *,
           data: bytes) -> HousekeepingPhoto:
    a = hk_assignments.get(db, property_id, assignment_id)
    hk_transitions.require_owner_or_manager(a, actor_id, role)
    if a.status != HkAssignmentStatus.in_progress:
        raise TransitionError("Photos can only be added while the room is being cleaned")
    if not data:
        raise ValidationFailed("A photo file is required", details={"photo": "required"})
    if len(data) > MAX_PHOTO_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    content_type = sniff_image_type(data)
    if content_type is None:
        raise ValidationFailed("A photo must be a JPEG, PNG or WebP image",
                               details={"photo": "unsupported_image_type"})
    photo = HousekeepingPhoto(assignment_id=a.id, property_id=property_id,
                              uploaded_by_user_id=actor_id, content_type=content_type,
                              byte_size=len(data), data=data)
    db.add(photo)
    db.flush()
    audit.record(db, property_id, actor_id, "housekeeping.photo_attached", "housekeeping_photo",
                 photo.id, after={"assignment_id": a.id, "byte_size": len(data)})
    hk_rooms.emit(db, property_id, [a.room_id])
    return photo


def get_photo(db: Session, property_id: str, assignment_id: str,
              photo_id: str) -> HousekeepingPhoto:
    """Scoped by property and assignment, never by the guessable id alone."""
    photo = db.scalar(select(HousekeepingPhoto).where(
        HousekeepingPhoto.id == photo_id, HousekeepingPhoto.property_id == property_id,
        HousekeepingPhoto.assignment_id == assignment_id))
    if photo is None:
        raise NotFound("Photo not found")
    return photo


def photo_url(property_id: str, assignment_id: str, photo_id: str) -> str:
    return f"/api/p/{property_id}/housekeeping/assignments/{assignment_id}/photos/{photo_id}"


def photos_for(db: Session, assignment_ids: list[str]) -> dict[str, list[HousekeepingPhoto]]:
    out: dict[str, list[HousekeepingPhoto]] = defaultdict(list)
    if not assignment_ids:
        return out
    for p in db.scalars(select(HousekeepingPhoto)
                        .where(HousekeepingPhoto.assignment_id.in_(assignment_ids))
                        .order_by(HousekeepingPhoto.created_at, HousekeepingPhoto.id)):
        out[p.assignment_id].append(p)
    return out
