"""
Places: approval, removal, deleting for good, and upgrading an older database.
The routes are in evac_routes.py (public add, remove, restore) and place_routes.py (staff).

The rules (docs/REDESIGN.md, "Map and places"):

  pending     A place a user adds. Only the phone that sent it (hashed phone ID) sees it.
  approved    A responder or Super admin approved it: everybody sees it.
  rejected    A responder or Super admin rejected it: nobody but staff sees it.
  removed     A responder or Super admin removed an approved center. Hidden for everyone and kept
              config.REMOVED_CENTERS_KEEP_DAYS days (30), then deleted together with its status
              history by purge_removed_centers(). A Super admin can delete it sooner.

"Hide on this phone" is NOT here on purpose: it lives in the browser only and the server never
hears about it. A user cannot remove or hide a center for anybody else.

Rejected places are deleted after the same number of days (counted from the rejection).

Like report_service, the functions that change data add the change and its audit entry to the
session and commit once at the end, so they are saved together or not at all.
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException, Request
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import audit, config, evac_service
from .database import SessionLocal
from .evac_service import APPROVED, EVAC_TYPE, PENDING, REJECTED
from .models import (
    ActionLog, DeletedFacility, Facility, FacilityRemoval, StatusUpdate, User, UserEvacuationCenter,
)
from .schemas import DuplicateOut, PlaceAdminOut, RemovalOut


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like the other tables


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt is not None else None


class PlaceError(HTTPException):
    def __init__(self, status_code: int, message: str):
        super().__init__(status_code=status_code, detail=message)


def _target(f: Facility) -> str:
    return f"place:{f.id} ({f.name})"


# ------------------------------------------------------------ upgrading an existing database

# Tables that got columns in part 3. Base.metadata.create_all makes missing TABLES but never adds a
# column to one that exists, so the columns are added here, keeping every row. Every column added
# this way needs a server_default in models.py if it is NOT NULL (SQLite cannot add one without).
_UPGRADED_MODELS = (UserEvacuationCenter, FacilityRemoval, StatusUpdate)


def upgrade_place_columns(engine) -> Dict[str, List[str]]:
    """
    Adds the part 3 columns to older tables: places get "approved" (they were public already),
    old status updates become "user" reports, old removals have no name. Does nothing on a new or
    already upgraded database. Returns {table: [columns it added]} for the tables it changed.
    """
    insp = inspect(engine)
    added: Dict[str, List[str]] = {}
    with engine.begin() as conn:
        for model in _UPGRADED_MODELS:
            table = model.__table__
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}"
                if col.server_default is not None:
                    ddl += f" DEFAULT '{col.server_default.arg}'"
                if not col.nullable:
                    ddl += " NOT NULL"
                conn.execute(text(ddl))
                added.setdefault(table.name, []).append(col.name)
        if insp.has_table(UserEvacuationCenter.__tablename__):
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_user_evacuation_centers_phone_hash "
                "ON user_evacuation_centers (phone_hash)"
            ))
    return added


# ------------------------------------------------------------ lookups

def get_center(db: Session, facility_id: int) -> Facility:
    """The facility, only if it is an evacuation center (hospitals and clinics cannot be removed or reviewed)."""
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise PlaceError(404, "Evacuation center not found.")
    if facility.type != EVAC_TYPE:
        raise PlaceError(422, "Only evacuation centers can be added, removed or restored here.")
    return facility


def get_user_place(db: Session, facility_id: int):
    """(facility, user row) of a place added through the app. 404 for anything else."""
    facility = db.get(Facility, facility_id)
    row = evac_service.user_row_for(db, facility.key) if facility is not None else None
    if facility is None or row is None:
        raise PlaceError(404, "Added place not found.")
    return facility, row


# ------------------------------------------------------------ what staff see of an added place

def _duplicate_of(db: Session, f: Facility, row: UserEvacuationCenter) -> Optional[DuplicateOut]:
    found = evac_service.find_duplicate(db, row.name, row.latitude, row.longitude, exclude_key=f.key)
    if found is None:
        return None
    other, removed = found
    other_row = evac_service.user_row_for(db, other.key)
    return DuplicateOut(
        id=other.id, key=other.key, name=other.name,
        distance_m=round(evac_service.distance_m(row.latitude, row.longitude, other.latitude, other.longitude), 1),
        approval_status=other_row.approval_status if other_row else APPROVED,
        removed=removed,
    )


def place_admin_out(db: Session, f: Facility, row: UserEvacuationCenter, message: Optional[str] = None) -> PlaceAdminOut:
    return PlaceAdminOut(
        id=f.id, key=f.key, name=row.name, center_type=row.center_type,
        barangay=row.barangay, address=row.address, contact=row.contact,
        max_capacity=row.max_capacity, latitude=row.latitude, longitude=row.longitude, note=row.note,
        approval_status=row.approval_status,
        submitted_at=_utc(row.created_at),
        reviewed_by=row.reviewed_by, reviewed_at=_utc(row.reviewed_at), reject_reason=row.reject_reason,
        possible_duplicate=_duplicate_of(db, f, row) if row.approval_status != APPROVED else None,
        is_removed=evac_service.active_removal(db, f.key) is not None,
        message=message,
    )


def list_places(db: Session, status: str = PENDING) -> List[PlaceAdminOut]:
    """
    Added places with this approval status. Pending: the longest-waiting first (a queue).
    Rejected: newest first. Each pending place carries its duplicate flag.
    """
    query = db.query(UserEvacuationCenter).filter(UserEvacuationCenter.approval_status == status)
    rows = query.order_by(UserEvacuationCenter.id.asc() if status == PENDING else UserEvacuationCenter.id.desc()).all()
    out = []
    for row in rows:
        f = db.query(Facility).filter(Facility.key == f"user:{row.id}").first()
        if f is not None:
            out.append(place_admin_out(db, f, row))
    return out


# ------------------------------------------------------------ approve / reject

def approve(db: Session, user: User, facility_id: int, request: Optional[Request]) -> PlaceAdminOut:
    """Pending (or rejected, to undo a mistake) -> approved: everybody sees it. Safe to call twice."""
    f, row = get_user_place(db, facility_id)
    if row.approval_status == APPROVED:
        return place_admin_out(db, f, row, "This place was already approved.")
    was = row.approval_status
    dup = _duplicate_of(db, f, row)
    row.approval_status = APPROVED
    row.reviewed_by, row.reviewed_at, row.reject_reason = user.name, _now(), None
    audit.record(
        db, user, "place.approve", target=_target(f),
        detail={"key": f.key, "was": was, "possible_duplicate_of": dup.key if dup else None}, request=request,
    )
    db.commit()
    return place_admin_out(db, f, row, "Place approved. Everyone can see it now.")


def reject(db: Session, user: User, facility_id: int, reason: Optional[str], request: Optional[Request]) -> PlaceAdminOut:
    """Pending -> rejected: only staff see it. An approved place is removed instead (409). Safe to call twice."""
    f, row = get_user_place(db, facility_id)
    if row.approval_status == REJECTED:
        return place_admin_out(db, f, row, "This place was already rejected.")
    if row.approval_status == APPROVED:
        raise PlaceError(409, "This place is already on the map. Remove it instead of rejecting it.")
    row.approval_status = REJECTED
    row.reviewed_by, row.reviewed_at, row.reject_reason = user.name, _now(), reason
    audit.record(db, user, "place.reject", target=_target(f), detail={"key": f.key, "reason": reason}, request=request)
    db.commit()
    return place_admin_out(db, f, row, "Place rejected.")


# ------------------------------------------------------------ remove / restore (staff)

def removal_out(f: Facility, removal: FacilityRemoval, message: Optional[str] = None) -> RemovalOut:
    delete_after = removal.removed_at + timedelta(days=config.REMOVED_CENTERS_KEEP_DAYS)
    seconds_left = (delete_after - _now()).total_seconds()
    return RemovalOut(
        id=f.id, key=f.key, name=f.name,
        removed_at=_utc(removal.removed_at), message=message,
        removed_by=removal.removed_by,
        delete_after=_utc(delete_after),
        days_left=max(0, math.ceil(seconds_left / 86400)),
    )


def remove(db: Session, user: User, facility_id: int, request: Optional[Request]) -> RemovalOut:
    """
    Remove an approved center for everyone. Its data and status history are kept for
    REMOVED_CENTERS_KEEP_DAYS days and it can be restored until then. Safe to call twice.
    """
    f = get_center(db, facility_id)
    existing = evac_service.active_removal(db, f.key)
    if existing:
        return removal_out(f, existing, "This evacuation center was already removed.")
    row = evac_service.user_row_for(db, f.key)
    if row is not None and row.approval_status == PENDING:
        raise PlaceError(409, "This place is waiting for approval. Reject it instead of removing it.")
    if row is not None and row.approval_status == REJECTED:
        raise PlaceError(409, "This place was rejected, so it is not on the map.")
    removal = evac_service.mark_removed(db, f.key, removed_by=user.name)
    audit.record(
        db, user, "place.remove", target=_target(f),
        detail={"key": f.key, "kept_days": config.REMOVED_CENTERS_KEEP_DAYS}, request=request,
    )
    db.commit()
    db.refresh(removal)
    return removal_out(f, removal, f"Evacuation center removed. It can be restored for {config.REMOVED_CENTERS_KEEP_DAYS} days.")


def restore(db: Session, user: User, facility_id: int, request: Optional[Request]) -> Facility:
    """Bring a removed center back on the map. A center that is not removed is returned as it is (nothing to do)."""
    f = get_center(db, facility_id)
    removal = evac_service.active_removal(db, f.key)
    if removal is None:
        return f
    evac_service.mark_restored(db, removal)
    audit.record(db, user, "place.restore", target=_target(f), detail={"key": f.key}, request=request)
    db.commit()
    return f


def list_removed(db: Session) -> List[RemovalOut]:
    """Centers that are removed right now, newest removal first, each with the day it will be deleted."""
    return [removal_out(f, r) for f, r in evac_service.removed_facilities(db)]


# ------------------------------------------------------------ deleting for good

def _delete_rows_for_key(db: Session, key: str) -> None:
    """
    Everything about one center: the facilities row, its status history, its removal history, its
    old action-log lines and (for an added place) the place itself. An OSM or manual center is
    noted in deleted_facilities so the next start does not read it from the data file again.
    The audit log is never touched.
    """
    f = db.query(Facility).filter(Facility.key == key).first()
    if f is not None:
        db.query(StatusUpdate).filter(StatusUpdate.facility_id == f.id).delete(synchronize_session=False)
        db.delete(f)
    db.query(FacilityRemoval).filter(FacilityRemoval.facility_key == key).delete(synchronize_session=False)
    db.query(ActionLog).filter(ActionLog.facility_key == key).delete(synchronize_session=False)
    if key.startswith("user:"):
        try:
            row = db.get(UserEvacuationCenter, int(key.split(":", 1)[1]))
        except ValueError:
            row = None
        if row is not None:
            db.delete(row)
    elif db.get(DeletedFacility, key) is None:
        db.add(DeletedFacility(key=key))


def delete_for_good(db: Session, user: User, facility_id: int, request: Optional[Request]) -> dict:
    """
    Super admin only (the route checks): delete a removed center, or a rejected place, now instead
    of waiting for the purge. The center and its status history are gone for good.
    """
    f = get_center(db, facility_id)
    row = evac_service.user_row_for(db, f.key)
    removed = evac_service.active_removal(db, f.key) is not None
    if not removed and not (row is not None and row.approval_status == REJECTED):
        raise PlaceError(409, "Only a removed center or a rejected place can be deleted for good. Remove it first.")
    audit.record(
        db, user, "place.delete", target=_target(f),
        detail={"key": f.key, "was": "removed" if removed else "rejected"}, request=request,
    )
    _delete_rows_for_key(db, f.key)
    db.commit()
    return {"message": "Deleted for good, together with its status history."}


# ------------------------------------------------------------ the purge

def purge_removed_centers(db: Session, now: Optional[datetime] = None) -> int:
    """
    Delete, with their status history, the centers that have been removed for more than
    REMOVED_CENTERS_KEEP_DAYS days, and the places that were rejected that long ago. Restored
    centers are not touched. Returns how many centers it deleted and writes one audit entry
    (as "(system)") when it deleted any. Safe to run any time, as often as you like.
    """
    cutoff = (now or _now()) - timedelta(days=config.REMOVED_CENTERS_KEEP_DAYS)
    keys: List[str] = []
    for r in db.query(FacilityRemoval).filter(FacilityRemoval.restored_at.is_(None), FacilityRemoval.removed_at < cutoff).all():
        if r.facility_key not in keys:
            keys.append(r.facility_key)
    for u in db.query(UserEvacuationCenter).filter(
        UserEvacuationCenter.approval_status == REJECTED, UserEvacuationCenter.reviewed_at < cutoff
    ).all():
        if f"user:{u.id}" not in keys:
            keys.append(f"user:{u.id}")

    names = {}
    for key in keys:
        f = db.query(Facility).filter(Facility.key == key).first()
        names[key] = f.name if f is not None else None
        _delete_rows_for_key(db, key)
    if keys:
        audit.record(
            db, None, "place.purge",
            detail={
                "deleted": len(keys), "older_than_days": config.REMOVED_CENTERS_KEEP_DAYS,
                "places": [{"key": k, "name": names[k]} for k in keys],
            },
        )
    db.commit()
    return len(keys)


def purge_on_startup() -> int:
    """Used when the server starts (see main.py). Never stops the server from starting."""
    db = SessionLocal()
    try:
        deleted = purge_removed_centers(db)
        if deleted:
            print(f"Deleted {deleted} removed or rejected place(s) older than {config.REMOVED_CENTERS_KEEP_DAYS} days.")
        return deleted
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"Could not purge removed places: {e}")
        return 0
    finally:
        db.close()
