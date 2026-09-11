from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain._patch import patch_changes
from app.errors import Conflict, NotFound
from app.models import Conversation, ResolutionCategory
from app.schemas.content import CategoryIn, CategoryOut, CategoryPatch


def list_tree(db: Session, property_id: str) -> list[CategoryOut]:
    rows = db.scalars(select(ResolutionCategory)
                      .where(ResolutionCategory.property_id == property_id)
                      .order_by(ResolutionCategory.name)).all()
    nodes = {r.id: CategoryOut(id=r.id, name=r.name, parent_id=r.parent_id, active=r.active,
                              children=[]) for r in rows}
    roots: list[CategoryOut] = []
    for r in rows:
        (nodes[r.parent_id].children if r.parent_id in nodes else roots).append(nodes[r.id])
    return roots


def get(db: Session, property_id: str, category_id: str) -> ResolutionCategory:
    c = db.scalar(select(ResolutionCategory).where(ResolutionCategory.id == category_id,
                                                   ResolutionCategory.property_id == property_id))
    if c is None:
        raise NotFound("Category not found")
    return c


def create(db: Session, property_id: str, data: CategoryIn) -> ResolutionCategory:
    if data.parent_id:
        get(db, property_id, data.parent_id)
    c = ResolutionCategory(property_id=property_id, **data.model_dump())
    db.add(c)
    db.flush()
    return c


def update(db: Session, property_id: str, category_id: str,
          data: CategoryPatch) -> ResolutionCategory:
    c = get(db, property_id, category_id)
    for k, v in patch_changes(ResolutionCategory, data).items():
        setattr(c, k, v)
    db.flush()
    return c


def delete(db: Session, property_id: str, category_id: str) -> None:
    c = get(db, property_id, category_id)
    if db.scalar(select(ResolutionCategory.id).where(ResolutionCategory.parent_id == c.id)):
        raise Conflict("Delete or move the child categories first")
    if db.scalar(select(Conversation.id).where(Conversation.resolution_category_id == c.id)):
        raise Conflict("Reassign the conversations using this category first")
    db.delete(c)
