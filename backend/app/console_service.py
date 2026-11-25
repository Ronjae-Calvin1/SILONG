"""Helpers for the Admin screens: the badge counts and the signed-in Admin's recent actions."""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from . import config, report_service
from .evac_service import EVAC_TYPE
from .models import AuditLog, Facility, FacilityRemoval, User, UserEvacuationCenter

# What counts as "handling" a report in "handled N reports today".
_TAKE, _RELEASE = "report.take", "report.release"
_CLOSERS = ("report.resolve", "report.mark_false", "report.verify")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def summary(db: Session, user: User) -> dict:
    now = _now()
    counts = report_service.admin_counts(db, user.name)
    pending_ids = [i for (i,) in db.query(UserEvacuationCenter.id).filter(UserEvacuationCenter.approval_status == "pending").all()]
    pending = 0
    if pending_ids:  # same rule as the pending list: the place must have its facility row
        pending = db.query(Facility).filter(Facility.key.in_([f"user:{i}" for i in pending_ids])).count()
    removed = (
        db.query(FacilityRemoval)
        .join(Facility, Facility.key == FacilityRemoval.facility_key)
        .filter(FacilityRemoval.restored_at.is_(None), Facility.type == EVAC_TYPE)
        .count()
    )
    return dict(server_time=now, pending_places=pending, removed_centers=removed, **counts)


def today_start_utc(now: Optional[datetime] = None) -> datetime:
    """Local midnight as naive UTC (fixed offset: config.ADMIN_DAY_UTC_OFFSET_HOURS)."""
    offset = timedelta(hours=config.ADMIN_DAY_UTC_OFFSET_HOURS)
    local = (now or _now()) + offset
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - offset


def my_activity(db: Session, user: User, limit: int) -> dict:
    now = _now()
    start = today_start_utc(now)
    mine = db.query(AuditLog).filter(AuditLog.actor_id == user.id, ~AuditLog.action.like("auth.%"))
    items = mine.order_by(AuditLog.id.desc()).limit(limit).all()

    # A report counts once however many times it was touched. A take that was released again does not count, and
    # neither does one that another Admin took over or released (their entries are read for the same reports).
    state: Dict[str, bool] = {}  # target -> counts as handled
    handling = (AuditLog.created_at >= start, AuditLog.action.in_((_TAKE, _RELEASE) + _CLOSERS))
    targets = [t for (t,) in mine.filter(*handling).with_entities(AuditLog.target).distinct() if t]
    if targets:
        for row in db.query(AuditLog).filter(*handling, AuditLog.target.in_(targets)).order_by(AuditLog.id).all():
            if row.action == _RELEASE:
                state[row.target] = False
            elif row.actor_id == user.id:
                state[row.target] = True
            elif row.action == _TAKE:  # somebody else took it over from me
                state[row.target] = False
    return dict(server_time=now, handled_today=sum(1 for v in state.values() if v), today_starts_at=start, items=items)
