"""Helpers for reading capacity / availability status (kept out of main.py)."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .models import StatusUpdate
from .schemas import OVERCROWD_FACTOR, AdminStatusOut, StatusIn, StatusOut

# Where an update came from, and the words people see for it (docs/REDESIGN.md, "Status and capacity").
USER, OFFICIAL = "user", "official"
SOURCE_LABEL = {USER: "Reported by a user", OFFICIAL: "Confirmed by official"}

# StatusUpdate.kind
REPORT, OVERRIDE, CAPACITY = "report", "override", "capacity"


def _as_utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; everything we store is UTC.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _source(row: StatusUpdate) -> str:
    return row.source if row.source in SOURCE_LABEL else USER


def to_status_out(row: StatusUpdate) -> StatusOut:
    updated = _as_utc(row.created_at)
    return StatusOut(
        id=row.id,
        status=row.status,
        people_inside=row.people_inside,
        max_capacity=row.max_capacity,
        resources=json.loads(row.resources) if row.resources else [],
        note=row.note,
        updated_at=updated,
        is_outdated=(datetime.now(timezone.utc) - updated) > config.OUTDATED_AFTER,
        source=_source(row),
        source_label=SOURCE_LABEL[_source(row)],
    )


def to_admin_status_out(row: StatusUpdate) -> AdminStatusOut:
    return AdminStatusOut(
        id=row.id,
        kind=row.kind or REPORT,
        status=row.status,
        people_inside=row.people_inside,
        max_capacity=row.max_capacity,
        resources=json.loads(row.resources) if row.resources else [],
        note=row.note,
        updated_at=_as_utc(row.created_at),
        source=_source(row),
        source_label=SOURCE_LABEL[_source(row)],
        changed_by=row.changed_by,
    )


# A capacity correction is a history row, but it is not a status report: it copies the status it
# sits on. So "the latest status" and the public history skip it; only the capacity lookups
# below and the staff history (admin_history) see it.
_IS_STATUS = StatusUpdate.kind != CAPACITY


def latest_status_by_facility(db: Session) -> Dict[int, StatusOut]:
    """Newest status update per facility. Newest = highest id (ids only ever go up)."""
    newest_ids = select(func.max(StatusUpdate.id)).where(_IS_STATUS).group_by(StatusUpdate.facility_id)
    rows = db.query(StatusUpdate).filter(StatusUpdate.id.in_(newest_ids)).all()
    return {r.facility_id: to_status_out(r) for r in rows}


def history(db: Session, facility_id: int, limit: int) -> List[StatusOut]:
    rows = (
        db.query(StatusUpdate)
        .filter(StatusUpdate.facility_id == facility_id, _IS_STATUS)
        .order_by(StatusUpdate.id.desc())
        .limit(limit)
        .all()
    )
    return [to_status_out(r) for r in rows]


def admin_history(db: Session, facility_id: int, limit: int) -> List[AdminStatusOut]:
    """Every row, newest first, including overrides and capacity corrections, with staff names."""
    rows = (
        db.query(StatusUpdate)
        .filter(StatusUpdate.facility_id == facility_id)
        .order_by(StatusUpdate.id.desc())
        .limit(limit)
        .all()
    )
    return [to_admin_status_out(r) for r in rows]


def latest_row(db: Session, facility_id: int) -> Optional[StatusUpdate]:
    """The newest status row (not a capacity correction), or None."""
    return (
        db.query(StatusUpdate)
        .filter(StatusUpdate.facility_id == facility_id, _IS_STATUS)
        .order_by(StatusUpdate.id.desc())
        .first()
    )


def latest_for(db: Session, facility_id: int) -> Optional[StatusOut]:
    rows = history(db, facility_id, 1)
    return rows[0] if rows else None


# ---- Capacity ----

@dataclass
class ResolvedStatus:
    status: str
    people_inside: Optional[int]
    max_capacity: Optional[int]
    message: Optional[str] = None  # set when the server changed the status


def resolve_status(payload: StatusIn, previous_max: Optional[int], locked_max: Optional[int] = None) -> ResolvedStatus:
    """
    THE capacity rule, in one place (the status route and the admin override call only this).

    - max_capacity: what the report sends, else the last known one, so a report
      that leaves it out keeps the number the center already has.
    - `locked_max` is set for a report from a user when an official has set the capacity of
      this center: the official number is kept, whatever the user sent (the form always sends
      the field), and `message` says so when the user sent a different one.
    - If people_inside >= max_capacity and the reported status is open or
      almost_full, it is saved as "full" and `message` says so. A reported
      "full" or "closed" is left alone.
    - people_inside far above max_capacity is treated as a typo (ValueError,
      which the route turns into a 422).
    """
    notes = []
    if locked_max is not None:
        max_cap = locked_max
        if payload.max_capacity is not None and payload.max_capacity != locked_max:
            notes.append(
                f"The maximum capacity ({locked_max}) was set by an official, so the number you sent was not used."
            )
    else:
        max_cap = payload.max_capacity or previous_max
    status = payload.status
    people = payload.people_inside
    if people is not None and max_cap is not None:
        if people > max_cap * OVERCROWD_FACTOR:
            raise ValueError("People inside is far higher than the maximum capacity. Please check the numbers.")
        if people >= max_cap and status in ("open", "almost_full"):
            status = "full"
            notes.append(
                f"People inside ({people}) has reached the maximum capacity ({max_cap}), "
                "so this center was saved as full."
            )
    return ResolvedStatus(status, people, max_cap, " ".join(notes) or None)


def _newest_max_capacity(db: Session, official_only: bool) -> Dict[int, int]:
    where = [StatusUpdate.max_capacity.isnot(None)]
    if official_only:
        where.append(StatusUpdate.source == OFFICIAL)
    newest_ids = select(func.max(StatusUpdate.id)).where(*where).group_by(StatusUpdate.facility_id)
    rows = db.query(StatusUpdate.facility_id, StatusUpdate.max_capacity).filter(StatusUpdate.id.in_(newest_ids)).all()
    return {facility_id: cap for facility_id, cap in rows}


def official_max_capacity_by_facility(db: Session) -> Dict[int, int]:
    """The capacity an official last set, per facility (official reports, overrides and corrections)."""
    return _newest_max_capacity(db, official_only=True)


def latest_max_capacity_by_facility(db: Session) -> Dict[int, int]:
    """The capacity to show, per facility: the official one when there is one, else the newest any report gave."""
    return {**_newest_max_capacity(db, official_only=False), **official_max_capacity_by_facility(db)}


def official_max_capacity(db: Session, facility_id: int) -> Optional[int]:
    """The capacity an official last set for this facility, or None (users may still change it)."""
    row = (
        db.query(StatusUpdate.max_capacity)
        .filter(
            StatusUpdate.facility_id == facility_id,
            StatusUpdate.source == OFFICIAL,
            StatusUpdate.max_capacity.isnot(None),
        )
        .order_by(StatusUpdate.id.desc())
        .first()
    )
    return row[0] if row else None


def effective_max_capacity(db: Session, facility_id: int, base_max: Optional[int]) -> Optional[int]:
    """The official capacity if there is one, else the last max_capacity from any report, else `base_max` (the number given when a center was added)."""
    official = official_max_capacity(db, facility_id)
    if official is not None:
        return official
    row = (
        db.query(StatusUpdate.max_capacity)
        .filter(StatusUpdate.facility_id == facility_id, StatusUpdate.max_capacity.isnot(None))
        .order_by(StatusUpdate.id.desc())
        .first()
    )
    return row[0] if row else base_max


def capacity_fields(latest: Optional[StatusOut], max_capacity: Optional[int]) -> dict:
    """people_inside / max_capacity / spaces_left / percent_full for an evacuation center."""
    people = latest.people_inside if latest else None
    known = people is not None and max_capacity is not None
    return dict(
        people_inside=people,
        max_capacity=max_capacity,
        spaces_left=max(0, max_capacity - people) if known else None,
        percent_full=round(people / max_capacity * 100, 1) if known else None,
    )
