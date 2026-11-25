"""Request/response shapes for help requests and hazard reports."""
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

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
    category: str  # required: what the hazard or need is (1 to 40 characters), e.g. "Flooded road", "Trapped"
    latitude: float = Field(allow_inf_nan=False)
    longitude: float = Field(allow_inf_nan=False)
    contact: Optional[str] = None  # required for a help request, optional for a hazard; Admins only
    note: Optional[str] = None  # optional, short
    people: Optional[StrictInt] = Field(default=None, ge=1, le=config.REPORT_PEOPLE_MAX)  # help requests only
    can_move: Optional[Literal["yes", "no", "unsure"]] = None  # help requests only

    @field_validator("category")
    @classmethod
    def _category_clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if not (1 <= len(v) <= config.REPORT_CATEGORY_MAX):
            raise ValueError(f"Category must be 1 to {config.REPORT_CATEGORY_MAX} characters.")
        return v

    @field_validator("contact")
    @classmethod
    def _contact_clean(cls, v):
        return _clean_text(v, config.REPORT_CONTACT_MAX, "Contact")

    @field_validator("note")
    @classmethod
    def _note_clean(cls, v):
        return _clean_text(v, config.REPORT_NOTE_MAX, "Note")

    @model_validator(mode="after")
    def _kind_rules(self):
        if self.kind == "help" and not self.contact:
            raise ValueError("A help request needs a contact (a phone number the Admins can call).")
        if self.kind == "hazard":
            if self.people is not None:
                raise ValueError("people can only be sent with a help request, not with a hazard report.")
            if self.can_move is not None:
                raise ValueError("can_move can only be sent with a help request, not with a hazard report.")
        return self

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
    category: Optional[str] = None  # empty only on reports sent before this field existed
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
    category: Optional[str] = None  # what it is (from the first report); the only detail the public gets


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


class AdminReportOut(BaseModel):
    """One line of the Admin list: a help request, or a hazard (all reports about the same place)."""
    id: int  # use this id in the action endpoints
    kind: Literal["help", "hazard"]
    status: Literal["new", "being_handled", "resolved", "false"]
    is_new_help: bool  # a help request nobody has taken yet (the red alert)
    category: Optional[str] = None  # what it is; for a hazard, from its first report
    categories: List[str] = []  # every different category sent for this hazard (one entry for a help request)
    people: Optional[int] = None  # help requests: how many people need help
    can_move: Optional[Literal["yes", "no", "unsure"]] = None  # help requests: can the person move?
    latitude: float  # exact
    longitude: float  # exact
    contacts: List[str]
    notes: List[str]
    created_at: datetime
    updated_at: datetime
    taken_by: Optional[str] = None  # the Admin handling it (name), null while New
    is_mine: bool = False  # Being handled by the signed-in Admin (the "Mine" chip)
    distance_m: Optional[float] = None  # metres from the lat/lon sent to the list; null otherwise
    closed_by: Optional[str] = None
    resolution_note: Optional[str] = None
    false_reason: Optional[str] = None
    verified: bool
    verified_by: Optional[str] = None
    hazard_state: Optional[Literal["pending", "unconfirmed", "verified"]] = None  # hazards only
    phones: int  # different phones that sent it
    report_count: int


class AdminListOut(BaseModel):
    server_time: datetime
    refresh_seconds: int  # poll about this often
    new_help_count: int  # help requests nobody has taken yet
    has_new_help: bool  # true = show the red "Needs help" alert
    latest_report_id: Optional[int] = None
    since: Optional[datetime] = None  # echo of the `since` filter, when one was sent
    items: List[AdminReportOut]


def _out_dt(d: dict, *names: str) -> dict:
    for n in names:
        d[n] = _utc(d.get(n))
    return d


def admin_item_out(item: dict) -> AdminReportOut:
    return AdminReportOut(**_out_dt(dict(item), "created_at", "updated_at"))


def admin_list_out(data: dict) -> AdminListOut:
    data = dict(data)
    data["server_time"] = _utc(data["server_time"])
    data["since"] = _utc(data.get("since"))
    data["items"] = [admin_item_out(i) for i in data["items"]]
    return AdminListOut(**data)


def my_report_out(d: dict) -> MyReportOut:
    return MyReportOut(**_out_dt(dict(d), "created_at", "updated_at"))
