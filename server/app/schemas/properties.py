from pydantic import Field

from app.schemas.common import CamelModel


class PropertySettingsOut(CamelModel):
    id: str
    name: str
    code: str
    timezone: str
    address: str | None = None
    phone: str | None = None
    sms_number: str | None = None
    brand: str | None = None
    currency: str
    logo_url: str | None = None
    primary_color: str | None = None


class PropertySettingsPatch(CamelModel):
    """`code` is intentionally absent: it is unique across the whole install and identifies the
    property, so renaming it is not a settings edit. `Property.settings` (an untyped JSON bag) is
    intentionally absent too — nothing in the UI needs it. `timezone`, `phone` and `sms_number`
    carry only their column lengths here; their real validation lives in app/domain/properties.py
    beside the reason each one is load-bearing."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=400)
    phone: str | None = Field(default=None, max_length=32)
    sms_number: str | None = Field(default=None, max_length=32)
    brand: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=16)
