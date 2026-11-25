"""Request/response shapes for weather, advisories, official sources and emergency numbers."""
import re
from datetime import datetime, timezone
from typing import List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from . import config
from .models import Advisory, AdvisorySource, EmergencyNumber
from .schemas import _clean_text


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Times are stored as naive UTC; send them out marked as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt is not None else None


def _required(v: Optional[str], max_len: int, label: str) -> str:
    cleaned = _clean_text(v, max_len, label)
    if not cleaned:
        raise ValueError(f"{label} cannot be empty.")
    return cleaned


def _clean_url(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("The link to the original source cannot be empty.")
    if len(v) > config.ADVISORY_URL_MAX:
        raise ValueError(f"The link is too long (max {config.ADVISORY_URL_MAX} characters).")
    parts = urlparse(v)
    if parts.scheme not in ("http", "https") or not parts.netloc or re.search(r"\s", v):
        raise ValueError("The link must be a web address that starts with http:// or https://.")
    return v


# ---------------------------------------------------------------- weather

class WeatherCurrentOut(BaseModel):
    temperature_c: float
    feels_like_c: Optional[float] = None
    humidity_percent: Optional[float] = None
    wind_kph: float
    wind_gust_kph: Optional[float] = None
    rain_mm: float  # rain in the last hour
    weather_code: int  # WMO code from Open-Meteo
    condition: str  # plain words for the code, e.g. "Light rain"
    is_day: Optional[bool] = None


class WeatherDayOut(BaseModel):
    date: str  # YYYY-MM-DD, Philippine time
    temp_max_c: float
    temp_min_c: float
    rain_mm: float
    rain_chance_percent: Optional[float] = None
    wind_max_kph: Optional[float] = None
    weather_code: int
    condition: str


class WeatherStripOut(BaseModel):
    headline: str  # what WeatherStrip shows as its title
    detail: str  # and as its second line


class WeatherOut(BaseModel):
    location: str
    latitude: float
    longitude: float
    current: WeatherCurrentOut
    daily: List[WeatherDayOut]
    cyclone: Optional[str] = None  # always null: no reliable source yet, the screen says "check PAGASA"
    fetched_at: datetime  # UTC. When this forecast was received from Open-Meteo.
    is_stale: bool  # true when Open-Meteo could not be reached and this is the last good forecast
    notice: Optional[str] = None  # plain-language line to show when is_stale
    strip: WeatherStripOut


# ---------------------------------------------------------------- advisories

class AdvisoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    details: str
    organization: str  # who issued it, e.g. "PAGASA"
    source_url: str  # link to the original
    pinned: bool = False

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        return _required(v, config.ADVISORY_TITLE_MAX, "The title")

    @field_validator("details")
    @classmethod
    def _details(cls, v):
        return _required(v, config.ADVISORY_DETAILS_MAX, "The details")

    @field_validator("organization")
    @classmethod
    def _org(cls, v):
        return _required(v, config.ADVISORY_SOURCE_MAX, "The source")

    @field_validator("source_url")
    @classmethod
    def _url(cls, v):
        return _clean_url(v)


class AdvisoryUpdateIn(BaseModel):
    """Only the fields that are sent change. Pinning has its own endpoints."""
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    details: Optional[str] = None
    organization: Optional[str] = None
    source_url: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        return None if v is None else _required(v, config.ADVISORY_TITLE_MAX, "The title")

    @field_validator("details")
    @classmethod
    def _details(cls, v):
        return None if v is None else _required(v, config.ADVISORY_DETAILS_MAX, "The details")

    @field_validator("organization")
    @classmethod
    def _org(cls, v):
        return None if v is None else _required(v, config.ADVISORY_SOURCE_MAX, "The source")

    @field_validator("source_url")
    @classmethod
    def _url(cls, v):
        return None if v is None else _clean_url(v)

    @model_validator(mode="after")
    def _something_to_change(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one thing to change.")
        return self


class AdvisoryOut(BaseModel):
    id: int
    title: str
    details: str
    summary: str  # same text as `details`: UpdatesTab calls it summary, WarningsTab calls it details
    organization: str
    source_url: str  # "Read Original Source" (UpdatesTab) / "View Official Bulletin" (WarningsTab)
    is_official: bool  # the organization is on the official list
    pinned: bool
    published_at: datetime  # UTC
    updated_at: Optional[datetime] = None


def advisory_out(a: Advisory, official: bool) -> AdvisoryOut:
    return AdvisoryOut(
        id=a.id, title=a.title, details=a.details, summary=a.details, organization=a.source,
        source_url=a.source_url, is_official=official, pinned=bool(a.pinned),
        published_at=_utc(a.created_at), updated_at=_utc(a.updated_at),
    )


class AdvisorySourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return _required(v, config.ADVISORY_SOURCE_MAX, "The name")


class AdvisorySourceOut(BaseModel):
    id: int
    name: str


def source_out(s: AdvisorySource) -> AdvisorySourceOut:
    return AdvisorySourceOut(id=s.id, name=s.name)


# ---------------------------------------------------------------- emergency numbers

_NUMBER_OK = re.compile(r"^[0-9+()\-*#\s]+$")


def _clean_number(v: str) -> str:
    cleaned = _required(v, config.EMERGENCY_NUMBER_MAX, "The number")
    if not _NUMBER_OK.match(cleaned) or sum(c.isdigit() for c in cleaned) < 3:
        raise ValueError("The number can only have digits, spaces and + - ( ), and at least 3 digits.")
    return cleaned


# What a number is for; the hotline sheet filters on it (same words as config.EMERGENCY_CATEGORIES).
EmergencyCategory = Literal["medical", "accident", "flood", "violence", "missing_person"]


class EmergencyNumberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: str
    name: str
    description: Optional[str] = None
    category: Optional[EmergencyCategory] = None  # leave out for a general number

    @field_validator("number")
    @classmethod
    def _number(cls, v):
        return _clean_number(v)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return _required(v, config.EMERGENCY_NAME_MAX, "The name")

    @field_validator("description")
    @classmethod
    def _description(cls, v):
        return _clean_text(v, config.EMERGENCY_DESCRIPTION_MAX, "The description")


class EmergencyNumberUpdateIn(BaseModel):
    """Only the fields that are sent change. Send "description": null (or "category": null) to clear it."""
    model_config = ConfigDict(extra="forbid")

    number: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[EmergencyCategory] = None

    @field_validator("number")
    @classmethod
    def _number(cls, v):
        return None if v is None else _clean_number(v)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return None if v is None else _required(v, config.EMERGENCY_NAME_MAX, "The name")

    @field_validator("description")
    @classmethod
    def _description(cls, v):
        return _clean_text(v, config.EMERGENCY_DESCRIPTION_MAX, "The description")

    @model_validator(mode="after")
    def _something_to_change(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one thing to change.")
        if "number" in self.model_fields_set and self.number is None:
            raise ValueError("The number cannot be empty.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("The name cannot be empty.")
        return self


class EmergencyOrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: List[int]  # every emergency number id, in the order to show them


class EmergencyNumberOut(BaseModel):
    id: int
    number: str
    name: str
    description: Optional[str] = None
    position: int
    category: Optional[EmergencyCategory] = None  # medical | accident | flood | violence | missing_person; null = general


def number_out(n: EmergencyNumber) -> EmergencyNumberOut:
    return EmergencyNumberOut(
        id=n.id, number=n.number, name=n.name, description=n.description, position=n.position,
        category=n.category if n.category in config.EMERGENCY_CATEGORIES else None,
    )


# ---------------------------------------------------------------- chat

class ChatIn(BaseModel):
    """One question. The length limit is checked by the route (plain message), not here."""
    model_config = ConfigDict(extra="forbid")
    question: str


class ChatOut(BaseModel):
    """Exactly what the AskSiloPanel screen reads (SiloAnswer in frontend/src/types)."""
    answer: str
    topic: Optional[str] = None  # the guide entry the answer came from; null = nothing matched
