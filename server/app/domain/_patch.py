from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import inspect

from app.errors import ValidationFailed


def patch_changes(model: type, data: BaseModel, *, required: tuple[str, ...] = ()) -> dict:
    """`model_dump(exclude_unset=True)`, refusing an explicit `null` on a field that cannot hold
    one (ruling D82).

    Every PATCH schema here declares its fields `T | None = None` so `exclude_unset` can tell
    "absent" from "present" — which makes an explicit `{"name": null}` indistinguishable from the
    optional type at the edge. Left alone the `None` reaches `setattr` and the NOT NULL constraint
    raises `IntegrityError` at flush time; `errors.py` registers no `IntegrityError` handler, so
    the caller gets a bare 500 (and on quick replies, a 409 blaming the shortcut, because the
    nested flush's `except IntegrityError` assumed a collision). An admin form that serialises a
    cleared input as `null` hits this on every required field.

    Rejecting is deliberate where skipping was the alternative: a skipped `null` returns 200 and
    silently discards the edit, which is the same silent no-op in a friendlier costume.

    `required` names fields that are not columns on `model` but still cannot be null — the typed
    keys this project stores inside `Property.settings`.
    """
    changes = data.model_dump(exclude_unset=True)
    columns = inspect(model).columns
    cleared = sorted(k for k, v in changes.items() if v is None
                     and (k in required or (k in columns and not columns[k].nullable)))
    if cleared:
        # Report the camelCase names the caller actually sent, so a form can map the failure back
        # to the input the admin cleared; `changes` stays snake_case for setattr.
        fields = type(data).model_fields
        wire = [fields[k].alias or k for k in cleared]
        raise ValidationFailed(f"Cannot be cleared: {', '.join(wire)}",
                               details={name: "required" for name in wire})
    return changes
