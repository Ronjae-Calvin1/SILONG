"""Request/response shapes for help requests and hazard reports."""
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import config
from .schemas import _clean_text

ACTION_TEXT_MIN, ACTION_TEXT_MAX = 3, 500


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Times are stored as naive UTC; send them out marked as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt is not None else None


class ReportIn(BaseModel):
    """
    What a phone may send. Nothing else is accepted: no name, no photo (a field
    that is not listed here is refused with 422). The phone ID goes in the
    X-Phone-Id header, not in the body.
    """
    model_config = ConfigDict(extra="forbid")

    kind: Literal["help", "hazard"]
    latitude: float = Field(allow_inf_nan=False)
    longitude: float = Field(allow_inf_nan=False)
    contact: Optional[str] = None  # optional; only responders and Super admins ever see it
    note: Optional[str] = None  # optional, short

    @field_validator("contact")
    @classmethod
    def _contact_clean(cls, v):
        return _clean_text(v, config.REPORT_CONTACT_MAX, "Contact")

    @field_validator("note")
    @classmethod
    def _note_clean(cls, v):
        return _clean_text(v, config.REPORT_NOTE_MAX, "Note")

    @model_validator(mode="after")
    def _inside_city(self):
        south, west, north, east = config.BATANGAS_CITY_BBOX
        if not (south <= self.latitude <= north and west <= self.longitude <= east):
            raise ValueError(
                "That location is outside Batangas City "
                f"(latitude {south} to {north}, longitude {west} to {east})."
            )
        return self


class ReportSentOut(BaseModel):
    id: int
    kind: Literal["help", "hazard"]
    status: Literal["new", "being_handled", "resolved"]
    label: str
    created_at: datetime
    message: str


class MyReportOut(BaseModel):
    """A phone's own report. No contact, no handler, no reason: only a status."""
    id: int
    kind: Literal["help", "hazard"]
    status: Literal["new", "being_handled", "resolved"]
    label: str  # New | Being handled | Resolved
    latitude: float
    longitude: float
    note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class NearbyHazardOut(BaseModel):
    """What the public sees of a hazard: an approximate spot and a status. Nothing else."""
    id: int
    latitude: float  # approximate
    longitude: float  # approximate
    status: Literal["unconfirmed", "verified"]
    label: str  # Unconfirmed | Verified


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what_was_done: str

    @field_validator("what_was_done")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if not (ACTION_TEXT_MIN <= len(v) <= ACTION_TEXT_MAX):
            raise ValueError(f"Say what was done ({ACTION_TEXT_MIN} to {ACTION_TEXT_MAX} characters).")
        return v


class MarkFalseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str

    @field_validator("reason")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if not (ACTION_TEXT_MIN <= len(v) <= ACTION_TEXT_MAX):
            raise ValueError(f"Give a reason ({ACTION_TEXT_MIN} to {ACTION_TEXT_MAX} characters).")
        return v


class ResponderReportOut(BaseModel):
    """One line of the responder list: a help request, or a hazard (all reports about the same place)."""
    id: int  # use this id in the action endpoints
    kind: Literal["help", "hazard"]
    status: Literal["new", "being_handled", "resolved", "false"]
    is_new_help: bool  # a help request nobody has taken yet (the red alert)
    latitude: float  # exact
    longitude: float  # exact
    contacts: List[str]
    notes: List[str]
    created_at: datetime
    updated_at: datetime
    taken_by: Optional[str] = None
    closed_by: Optional[str] = None
    resolution_note: Optional[str] = None
    false_reason: Optional[str] = None
    verified: bool
    verified_by: Optional[str] = None
    hazard_state: Optional[Literal["pending", "unconfirmed", "verified"]] = None  # hazards only
    phones: int  # different phones that sent it
    report_count: int


class ResponderListOut(BaseModel):
    server_time: datetime
    refresh_seconds: int  # poll about this often
    new_help_count: int  # help requests nobody has taken yet
    has_new_help: bool  # true = show the red "Needs help" alert
    latest_report_id: Optional[int] = None
    items: List[ResponderReportOut]


def _out_dt(d: dict, *names: str) -> dict:
    for n in names:
        d[n] = _utc(d.get(n))
    return d


def responder_item_out(item: dict) -> ResponderReportOut:
    return ResponderReportOut(**_out_dt(dict(item), "created_at", "updated_at"))


def responder_list_out(data: dict) -> ResponderListOut:
    data = dict(data)
    data["server_time"] = _utc(data["server_time"])
    data["items"] = [responder_item_out(i) for i in data["items"]]
    return ResponderListOut(**data)


def my_report_out(d: dict) -> MyReportOut:
    return MyReportOut(**_out_dt(dict(d), "created_at", "updated_at"))
