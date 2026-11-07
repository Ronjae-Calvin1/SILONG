"""
Evacuation center manager: stable identity, duplicates, soft delete, action log.

Identity: every center has a `key` that comes from where it came from and does
not depend on the database file:
    osm:way/123                 from OpenStreetMap (facilities.json)
    manual:<type>:<name-slug>   from manual_facilities.json
    user:<n>                    added through the API
`facilities.id` (the number the API uses in URLs) is kept across restarts by
matching rows on this key; see main.sync_facilities.
"""
import hashlib
import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from . import config, status_service
from .models import ActionLog, Facility, FacilityRemoval, UserEvacuationCenter
from .schemas import EvacCenterIn, FacilityOut, StatusOut

EVAC_TYPE = "evacuation_center"


def _now() -> datetime:
    # Always UTC and naive, like the other tables (SQLite keeps no time zones).
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---- Identity ----

def source_of(key: str) -> str:
    """"osm" | "manual" | "user", read from the key prefix."""
    prefix = key.split(":", 1)[0]
    return prefix if prefix in ("osm", "manual", "user") else "manual"


def user_center_facility_fields(row: UserEvacuationCenter) -> dict:
    """The `facilities` columns that mirror a user-added center."""
    barangay = row.barangay
    if barangay and not re.match(r"(brgy|barangay)\b", barangay, re.I):
        barangay = f"Brgy. {barangay}"
    address = ", ".join(p for p in (row.address, barangay, "Batangas City") if p)
    return dict(
        name=row.name, type=EVAC_TYPE,
        latitude=row.latitude, longitude=row.longitude,
        address=address, contact=row.contact, notes=row.note,
    )


# ---- Duplicates ----

def normalize_name(name: str) -> str:
    """Lowercase, no accents or punctuation, single spaces: "Brgy. Alangilan Gym" ~ "brgy alangilan gym"."""
    plain = unicodedata.normalize("NFKD", name)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.casefold()).split())


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(a))


def find_duplicate(db: Session, name: str, lat: float, lng: float) -> Optional[Tuple[Facility, bool]]:
    """
    An existing evacuation center with the same normalized name within
    config.DUPLICATE_METERS. Removed centers count too (second value True), so
    the caller can tell the person to restore it instead of adding it again.
    """
    wanted = normalize_name(name)
    removed = removed_keys(db)
    for f in db.query(Facility).filter(Facility.type == EVAC_TYPE).all():
        if normalize_name(f.name) == wanted and distance_m(lat, lng, f.latitude, f.longitude) <= config.DUPLICATE_METERS:
            return f, f.key in removed
    return None


# ---- Soft delete ----

def removed_keys(db: Session) -> set:
    rows = db.query(FacilityRemoval.facility_key).filter(FacilityRemoval.restored_at.is_(None)).all()
    return {key for (key,) in rows}


def active_removal(db: Session, key: str) -> Optional[FacilityRemoval]:
    return (
        db.query(FacilityRemoval)
        .filter(FacilityRemoval.facility_key == key, FacilityRemoval.restored_at.is_(None))
        .order_by(FacilityRemoval.id.desc())
        .first()
    )


def mark_removed(db: Session, key: str) -> FacilityRemoval:
    row = FacilityRemoval(facility_key=key)
    db.add(row)
    return row


def mark_restored(db: Session, removal: FacilityRemoval) -> None:
    removal.restored_at = _now()


# ---- Action log ----

def hash_ip(ip: str) -> str:
    """One-way hash: lets us see "same connection" without storing the address."""
    return hashlib.sha256(f"{config.IP_HASH_SALT}:{ip}".encode()).hexdigest()


def log_action(db: Session, action: str, key: str, ip: str) -> None:
    db.add(ActionLog(action=action, facility_key=key, ip_hash=hash_ip(ip)))


# ---- Adding ----

def create_center(db: Session, payload: EvacCenterIn) -> Facility:
    """Insert the user center and its facilities row. The caller commits."""
    row = UserEvacuationCenter(
        name=payload.name, center_type=payload.center_type,
        barangay=payload.barangay, address=payload.address, contact=payload.contact,
        max_capacity=payload.max_capacity,
        latitude=payload.latitude, longitude=payload.longitude, note=payload.note,
    )
    db.add(row)
    db.flush()  # assigns row.id, which makes the key
    facility = Facility(key=f"user:{row.id}", **user_center_facility_fields(row))
    db.add(facility)
    db.flush()
    return facility


# ---- Output ----

def to_facility_out(
    f: Facility,
    latest: Optional[StatusOut],
    user_row: Optional[UserEvacuationCenter],
    status_max: Optional[int],
) -> FacilityOut:
    """
    One facility as the API shows it. `status_max` is the newest max_capacity any
    report gave; `user_row` supplies the number a user-added center started with.
    """
    out = FacilityOut.model_validate(f)  # `status` is empty on the row itself
    out.source = source_of(f.key)
    out.status = latest
    out.is_outdated = latest.is_outdated if latest else None
    if f.type == EVAC_TYPE:
        out.center_type = user_row.center_type if user_row else None
        base_max = user_row.max_capacity if user_row else None
        for field, value in status_service.capacity_fields(latest, status_max or base_max).items():
            setattr(out, field, value)
    return out


def user_row_for(db: Session, key: str) -> Optional[UserEvacuationCenter]:
    if not key.startswith("user:"):
        return None
    try:
        return db.get(UserEvacuationCenter, int(key.split(":", 1)[1]))
    except ValueError:
        return None


def facility_out_for(db: Session, f: Facility) -> FacilityOut:
    """Same as the list endpoint, for a single facility."""
    return to_facility_out(
        f,
        status_service.latest_for(db, f.id),
        user_row_for(db, f.key),
        status_service.effective_max_capacity(db, f.id, None),
    )


def removed_facilities(db: Session) -> List[Tuple[Facility, FacilityRemoval]]:
    """Currently removed evacuation centers, newest removal first."""
    out = []
    for removal in (
        db.query(FacilityRemoval)
        .filter(FacilityRemoval.restored_at.is_(None))
        .order_by(FacilityRemoval.id.desc())
        .all()
    ):
        f = db.query(Facility).filter(Facility.key == removal.facility_key, Facility.type == EVAC_TYPE).first()
        if f is not None:
            out.append((f, removal))
    return out
