"""Helpers for reading capacity / availability status (kept out of main.py)."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .models import StatusUpdate
from .schemas import OVERCROWD_FACTOR, StatusIn, StatusOut


def _as_utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; everything we store is UTC.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


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
    )


def latest_status_by_facility(db: Session) -> Dict[int, StatusOut]:
    """Newest update per facility. Newest = highest id (ids only ever go up)."""
    newest_ids = select(func.max(StatusUpdate.id)).group_by(StatusUpdate.facility_id)
    rows = db.query(StatusUpdate).filter(StatusUpdate.id.in_(newest_ids)).all()
    return {r.facility_id: to_status_out(r) for r in rows}


def history(db: Session, facility_id: int, limit: int) -> List[StatusOut]:
    rows = (
        db.query(StatusUpdate)
        .filter(StatusUpdate.facility_id == facility_id)
        .order_by(StatusUpdate.id.desc())
        .limit(limit)
        .all()
    )
    return [to_status_out(r) for r in rows]


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


def resolve_status(payload: StatusIn, previous_max: Optional[int]) -> ResolvedStatus:
    """
    THE capacity rule, in one place (the status route calls only this).

    - max_capacity: what the report sends, else the last known one, so a report
      that leaves it out keeps the number the center already has.
    - If people_inside >= max_capacity and the reported status is open or
      almost_full, it is saved as "full" and `message` says so. A reported
      "full" or "closed" is left alone.
    - people_inside far above max_capacity is treated as a typo (ValueError,
      which the route turns into a 422).
    """
    max_cap = payload.max_capacity or previous_max
    status, message = payload.status, None
    people = payload.people_inside
    if people is not None and max_cap is not None:
        if people > max_cap * OVERCROWD_FACTOR:
            raise ValueError("People inside is far higher than the maximum capacity. Please check the numbers.")
        if people >= max_cap and status in ("open", "almost_full"):
            status = "full"
            message = (
                f"People inside ({people}) has reached the maximum capacity ({max_cap}), "
                "so this center was saved as full."
            )
    return ResolvedStatus(status, people, max_cap, message)


def latest_max_capacity_by_facility(db: Session) -> Dict[int, int]:
    """Newest max_capacity that any report gave, per facility."""
    newest_ids = (
        select(func.max(StatusUpdate.id))
        .where(StatusUpdate.max_capacity.isnot(None))
        .group_by(StatusUpdate.facility_id)
    )
    rows = db.query(StatusUpdate.facility_id, StatusUpdate.max_capacity).filter(StatusUpdate.id.in_(newest_ids)).all()
    return {facility_id: cap for facility_id, cap in rows}


def effective_max_capacity(db: Session, facility_id: int, base_max: Optional[int]) -> Optional[int]:
    """Last max_capacity from any report, else `base_max` (the number given when a center was added)."""
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
