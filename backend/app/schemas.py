"""Pydantic schemas — request/response shapes for the API."""
from datetime import datetime
from typing import Annotated, Literal, Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import config


# ---- Capacity and availability (status) ----

# Allowed values (from the project documentation).
EVAC_STATUSES = ("open", "almost_full", "full", "closed")
CLINIC_STATUSES = ("open", "busy", "full", "closed")  # hospitals and clinics
ALL_STATUSES = ("open", "almost_full", "busy", "full", "closed")
RESOURCES = ("space", "food", "water", "power", "toilets", "medical")

NOTE_MAX = 140
COUNT_MAX = 100_000
# People inside may exceed the stated capacity a little (crowding happens in a
# storm), but more than this many times the capacity is treated as a typo.
OVERCROWD_FACTOR = 2

_TYPE_NAME = {"hospital": "hospital", "clinic": "clinic", "evacuation_center": "evacuation center"}

Count = Annotated[int, Field(strict=True, ge=0, le=COUNT_MAX)]
# A maximum capacity of 0 makes no sense (everything would count as full).
Capacity = Annotated[int, Field(strict=True, ge=1, le=config.MAX_CAPACITY_LIMIT)]


def _clean_text(v: Optional[str], max_len: int, label: str) -> Optional[str]:
    """Trim, turn newlines/tabs into single spaces, reject (never cut) if too long."""
    if v is None:
        return None
    v = " ".join(v.split())
    if len(v) > max_len:
        raise ValueError(f"{label} is too long (max {max_len} characters).")
    return v or None


class StatusIn(BaseModel):
    """What a user may send. Nothing else (name, address, phone) is accepted."""
    model_config = ConfigDict(extra="forbid")

    status: str
    people_inside: Optional[Count] = None
    max_capacity: Optional[Capacity] = None
    resources: Optional[List[str]] = None
    note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status_known(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALL_STATUSES:
            raise ValueError(f"Unknown status '{v}'. Use one of: {', '.join(ALL_STATUSES)}.")
        return v

    @field_validator("resources")
    @classmethod
    def _resources_known(cls, v):
        if v is None:
            return None
        cleaned = [r.strip().lower() for r in v]
        bad = [r for r in cleaned if r not in RESOURCES]
        if bad:
            raise ValueError(f"Unknown resource '{bad[0]}'. Use any of: {', '.join(RESOURCES)}.")
        # Remove duplicates, keep the documented order.
        return [r for r in RESOURCES if r in cleaned] or None

    @field_validator("note")
    @classmethod
    def _note_clean(cls, v):
        return _clean_text(v, NOTE_MAX, "Note")

    @model_validator(mode="after")
    def _counts_make_sense(self):
        if self.people_inside is not None and self.max_capacity is not None:
            if self.people_inside > self.max_capacity * OVERCROWD_FACTOR:
                raise ValueError(
                    "People inside is far higher than the maximum capacity. Please check the numbers."
                )
        return self


def validate_for_facility_type(payload: StatusIn, facility_type: str) -> None:
    """
    Rules that depend on the facility's type. Raises ValueError with a message
    that is safe to show to the user (the route turns it into a 422).
    """
    name = _TYPE_NAME.get(facility_type, facility_type)
    allowed = EVAC_STATUSES if facility_type == "evacuation_center" else CLINIC_STATUSES
    article = "an" if name[0] in "aeiou" else "a"
    if payload.status not in allowed:
        raise ValueError(
            f"Status '{payload.status}' is not valid for {article} {name}. Allowed: {', '.join(allowed)}."
        )
    if facility_type != "evacuation_center" and (
        payload.people_inside is not None or payload.max_capacity is not None or payload.resources
    ):
        raise ValueError(
            f"A {name} only accepts a status and a short note (no people count, capacity or resources)."
        )


class StatusOut(BaseModel):
    id: int
    status: str
    people_inside: Optional[int] = None
    max_capacity: Optional[int] = None
    resources: List[str] = []
    note: Optional[str] = None
    updated_at: datetime  # UTC
    is_outdated: bool  # computed on the server, see config.OUTDATED_AFTER
    # Only set on the response to a new report, when the server changed what was
    # sent (for example people_inside reached max_capacity, so it saved "full").
    message: Optional[str] = None


# ---- Facilities ----

class FacilityOut(BaseModel):
    id: int
    # Stable identity from the data source ("osm:way/1", "manual:...", "user:3").
    # Unlike `id` it does not depend on the database file.
    key: Optional[str] = None
    name: str
    type: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None
    source: str = ""  # "osm" | "manual" | "user"
    center_type: Optional[str] = None  # "permanent" | "temporary"; only for user-added centers
    # Latest status update, or null if nobody has reported yet ("No status yet").
    status: Optional[StatusOut] = None
    # Capacity fields: evacuation centers only (null for hospitals and clinics,
    # and null for any number we do not know yet).
    people_inside: Optional[int] = None
    max_capacity: Optional[int] = None
    spaces_left: Optional[int] = None
    percent_full: Optional[float] = None  # can pass 100 when a center is over capacity
    is_outdated: Optional[bool] = None  # same as status.is_outdated; null when there is no status

    class Config:
        from_attributes = True


# ---- Evacuation center manager ----

NAME_MIN, NAME_MAX = 2, 100
BARANGAY_MAX, ADDRESS_MAX, CONTACT_MAX = 80, 200, 60


class EvacCenterIn(BaseModel):
    """What a manager sends to add a center. Nothing else is accepted."""
    model_config = ConfigDict(extra="forbid")

    name: str
    center_type: Literal["permanent", "temporary"]
    barangay: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    max_capacity: Capacity
    latitude: float = Field(allow_inf_nan=False)
    longitude: float = Field(allow_inf_nan=False)
    note: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if not (NAME_MIN <= len(v) <= NAME_MAX):
            raise ValueError(f"Name must be {NAME_MIN} to {NAME_MAX} characters.")
        return v

    @field_validator("barangay")
    @classmethod
    def _barangay_clean(cls, v):
        return _clean_text(v, BARANGAY_MAX, "Barangay")

    @field_validator("address")
    @classmethod
    def _address_clean(cls, v):
        return _clean_text(v, ADDRESS_MAX, "Address")

    @field_validator("contact")
    @classmethod
    def _contact_clean(cls, v):
        return _clean_text(v, CONTACT_MAX, "Contact")

    @field_validator("note")
    @classmethod
    def _note_clean(cls, v):
        return _clean_text(v, NOTE_MAX, "Note")

    @model_validator(mode="after")
    def _inside_city(self):
        south, west, north, east = config.BATANGAS_CITY_BBOX
        if not (south <= self.latitude <= north and west <= self.longitude <= east):
            raise ValueError(
                "That location is outside Batangas City "
                f"(latitude {south} to {north}, longitude {west} to {east})."
            )
        return self


class RemovalOut(BaseModel):
    id: int
    key: str
    name: str
    removed_at: datetime  # UTC
    message: Optional[str] = None


# ---- Weather ----

class WeatherWarning(BaseModel):
    signal: Optional[int] = None  # PAGASA wind signal number, if applicable
    headline: str
    description: str


class WeatherOut(BaseModel):
    location: str
    temperature_c: float
    condition: str
    wind_kph: float
    rain_mm: float
    warnings: List[WeatherWarning] = []
    fetched_at: str


# ---- AI: personalized prep plan ----

class HouseholdInput(BaseModel):
    household_size: int
    has_infant: bool = False
    has_elderly: bool = False
    has_pets: bool = False
    has_medical_needs: bool = False
    house_type: Optional[str] = None  # e.g. "concrete", "wood", "low-lying area"


class PrepPlanOut(BaseModel):
    checklist: List[str]
    notes: Optional[str] = None


# ---- AI: weather explainer ----

class WeatherExplainerOut(BaseModel):
    summary: str
    recommended_actions: List[str]


# ---- AI: damage report drafter ----

class DamageReportInput(BaseModel):
    description: str  # free text from the user, any language


class DamageReportOut(BaseModel):
    structured_report: str
    affected_count: Optional[int] = None
    needs: List[str] = []


# ---- AI: ask box (fallback / online mode) ----

class AskInput(BaseModel):
    question: str
    stage: Optional[str] = None  # "before" | "during" | "after"


class AskOut(BaseModel):
    answer: str
    source: str  # "ai" | "local_guide"
