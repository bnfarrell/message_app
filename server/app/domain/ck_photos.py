"""Checklist photos (checklists spec §3.3). Bytes in the table with `data` deferred, exactly as
work_order_photo and pm_run_photo, because the deployment filesystem is ephemeral."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, ck_instances
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import NotFound, TransitionError, ValidationFailed
from app.models import ChecklistPhoto, ChecklistTemplate, ChecklistTemplateItem
from app.schemas.enums import ChecklistStatus, PmItemType, Role


def attach(db: Session, property_id: str, actor_id: str, role: Role, instance_id: str, *,
           data: bytes, item_id: str | None) -> ChecklistPhoto:
    inst = ck_instances.get(db, property_id, instance_id)
    template = db.get(ChecklistTemplate, inst.template_id)
    ck_instances.require_actor(db, inst, template, actor_id, role)
    if inst.status != ChecklistStatus.in_progress:
        raise TransitionError("Photos can only be added while the checklist is in progress")
    if item_id is not None:
        item = db.scalar(select(ChecklistTemplateItem).where(
            ChecklistTemplateItem.id == item_id,
            ChecklistTemplateItem.template_id == inst.template_id))
        if item is None or item.item_type != PmItemType.photo:
            raise ValidationFailed("That item does not take a photo",
                                   details={"itemId": "not_a_photo_item"})
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
    photo = ChecklistPhoto(instance_id=inst.id, property_id=property_id, item_id=item_id,
                           uploaded_by_user_id=actor_id, content_type=content_type,
                           byte_size=len(data), data=data)
    db.add(photo)
    db.flush()
    audit.record(db, property_id, actor_id, "checklist.photo_attached", "checklist_photo",
                 photo.id, after={"instance_id": inst.id, "byte_size": len(data)})
    ck_instances.emit(db, property_id, [inst.id])
    return photo


def get_photo(db: Session, property_id: str, instance_id: str,
              photo_id: str) -> ChecklistPhoto:
    """Scoped by property and instance, never by the guessable id alone."""
    photo = db.scalar(select(ChecklistPhoto).where(
        ChecklistPhoto.id == photo_id, ChecklistPhoto.property_id == property_id,
        ChecklistPhoto.instance_id == instance_id))
    if photo is None:
        raise NotFound("Photo not found")
    return photo


def photo_url(property_id: str, instance_id: str, photo_id: str) -> str:
    return f"/api/p/{property_id}/checklists/instances/{instance_id}/photos/{photo_id}"


def photos_for(db: Session, instance_id: str) -> list[ChecklistPhoto]:
    return list(db.scalars(select(ChecklistPhoto)
                           .where(ChecklistPhoto.instance_id == instance_id)
                           .order_by(ChecklistPhoto.created_at, ChecklistPhoto.id)).all())
