"""Helpers for reading capacity / availability status (kept out of main.py)."""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .models import StatusUpdate
from .schemas import StatusOut


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
