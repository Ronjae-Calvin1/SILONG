"""Request/response shapes for the contact settings."""
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from . import config
from .content_schemas import _clean_number
from .schemas import _clean_text

_EMAIL_OK = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt is not None else None


def _optional_number(v: Optional[str]) -> Optional[str]:
    """An empty value clears the setting (null); anything else follows the emergency number rules."""
    cleaned = _clean_text(v, config.EMERGENCY_NUMBER_MAX, "The number")
    return None if cleaned is None else _clean_number(cleaned)


class ContactSettingsIn(BaseModel):
    """Only the fields that are sent change. Send null (or an empty text) to clear one."""
    model_config = ConfigDict(extra="forbid")

    control_room_number: Optional[str] = None
    support_email: Optional[str] = None
    support_number: Optional[str] = None

    @field_validator("control_room_number", "support_number")
    @classmethod
    def _numbers(cls, v):
        return _optional_number(v)

    @field_validator("support_email")
    @classmethod
    def _email(cls, v):
        cleaned = _clean_text(v, config.SETTING_EMAIL_MAX, "The email")
        if cleaned is not None and not _EMAIL_OK.match(cleaned):
            raise ValueError("That does not look like an email address.")
        return cleaned

    @model_validator(mode="after")
    def _something_to_change(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one thing to change.")
        return self


class SupportContactOut(BaseModel):
    """What the public Contact screen reads. Never the control-room number."""
    support_email: Optional[str] = None  # null = not set
    support_number: Optional[str] = None  # null = not set


class ContactSettingsOut(BaseModel):
    """What Admins read: all three. null = not set."""
    control_room_number: Optional[str] = None
    support_email: Optional[str] = None
    support_number: Optional[str] = None
    updated_at: Optional[datetime] = None  # latest change to any of the three
    updated_by: Optional[str] = None
