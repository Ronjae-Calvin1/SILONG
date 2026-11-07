"""
Evacuation center manager endpoints: add, remove (soft), restore.
No accounts, so the only protection is the per-IP limit (rate_limit.manage_limiter)
and the action log (hashed IP). Nothing here ever deletes a database row.
"""
from datetime import timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config, evac_service
from .database import get_db
from .models import Facility
from .rate_limit import manage_limiter
from .schemas import EvacCenterIn, FacilityOut, RemovalOut

router = APIRouter(prefix="/api/evacuation-centers", tags=["evacuation centers"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit(request: Request) -> None:
    """429 with a friendly message when this IP has used up its add/remove/restore allowance."""
    wait = manage_limiter.check(_ip(request))
    if wait is not None:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many changes from your connection. Please try again in about {minutes} minute(s).",
            headers={"Retry-After": str(wait)},
        )


def _get_center(db: Session, facility_id: int) -> Facility:
    """The facility, only if it is an evacuation center (hospitals and clinics cannot be removed)."""
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Evacuation center not found.")
    if facility.type != evac_service.EVAC_TYPE:
        raise HTTPException(status_code=422, detail="Only evacuation centers can be added, removed or restored here.")
    return facility


def _removal_out(facility: Facility, removal, message=None) -> RemovalOut:
    removed_at = removal.removed_at.replace(tzinfo=timezone.utc)  # stored as naive UTC
    return RemovalOut(id=facility.id, key=facility.key, name=facility.name, removed_at=removed_at, message=message)


@router.post("", response_model=FacilityOut, status_code=201)
def add_center(payload: EvacCenterIn, request: Request, db: Session = Depends(get_db)):
    """Add an evacuation center. Field rules live in schemas.EvacCenterIn."""
    dup = evac_service.find_duplicate(db, payload.name, payload.latitude, payload.longitude)
    if dup:
        existing, was_removed = dup
        hint = (
            f"It was removed earlier - restore it instead (POST /api/evacuation-centers/{existing.id}/restore)."
            if was_removed else "Please update that one instead of adding it again."
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"An evacuation center named '{existing.name}' already exists within "
                f"{config.DUPLICATE_METERS} m of this location (id {existing.id}). {hint}"
            ),
        )
    # Limit after validation and the duplicate check, so a mistake does not use up the allowance.
    _limit(request)

    facility = evac_service.create_center(db, payload)
    evac_service.log_action(db, "add", facility.key, _ip(request))
    db.commit()
    db.refresh(facility)
    return evac_service.facility_out_for(db, facility)


@router.get("/removed", response_model=List[RemovalOut])
def list_removed(db: Session = Depends(get_db)):
    """Centers that are currently removed, so one can be restored."""
    return [_removal_out(f, r) for f, r in evac_service.removed_facilities(db)]


@router.delete("/{facility_id}", response_model=RemovalOut)
def remove_center(facility_id: int, request: Request, db: Session = Depends(get_db)):
    """Soft remove: hides the center from the map. Its data and status history are kept."""
    facility = _get_center(db, facility_id)
    existing = evac_service.active_removal(db, facility.key)
    if existing:  # a second click or retry: nothing to do
        return _removal_out(facility, existing, "This evacuation center was already removed.")
    _limit(request)

    removal = evac_service.mark_removed(db, facility.key)
    evac_service.log_action(db, "remove", facility.key, _ip(request))
    db.commit()
    db.refresh(removal)
    return _removal_out(facility, removal, "Evacuation center removed. It can be restored.")


@router.post("/{facility_id}/restore", response_model=FacilityOut)
def restore_center(facility_id: int, request: Request, db: Session = Depends(get_db)):
    """Bring a removed center back on the map."""
    facility = _get_center(db, facility_id)
    removal = evac_service.active_removal(db, facility.key)
    if removal is None:  # not removed: nothing to do
        return evac_service.facility_out_for(db, facility)
    _limit(request)

    evac_service.mark_restored(db, removal)
    evac_service.log_action(db, "restore", facility.key, _ip(request))
    db.commit()
    return evac_service.facility_out_for(db, facility)
