"""
Staff changes to a status: override the latest status, correct the capacity.

An override or a correction is a NEW row in the status history. Nothing is edited or erased, the
row records the staff member's name (StatusUpdate.changed_by) and the action goes to the audit log
with the same name. Both count as "Confirmed by official" (source "official").

  override   replaces the latest status. Same fields and rules as a user report (status_service.resolve_status).
  capacity   changes only the maximum capacity of an evacuation center. It copies the status it
             sits on (kind "capacity"), so it never shows up as a status and does not make an old
             status look fresh. After it, users can no longer change that capacity with a report
             (status_service.resolve_status, `locked_max`); a later official change still can.

Like report_service, the functions add the row and the audit entry and commit once.
"""
import json
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import audit, evac_service, status_service
from .models import Facility, StatusUpdate, User
from .schemas import CapacityCorrectionIn, FacilityOut, StatusOut, StatusOverrideIn, OVERCROWD_FACTOR, validate_for_facility_type


def _facility(db: Session, facility_id: int) -> Facility:
    """A facility everybody can see. Staff work on what is on the map (use restore / approve first)."""
    f = evac_service.get_visible_facility(db, facility_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Facility not found.")
    return f


def _target(f: Facility) -> str:
    return f"facility:{f.id} ({f.name})"


def override_status(
    db: Session, user: User, facility_id: int, payload: StatusOverrideIn, request: Optional[Request]
) -> StatusOut:
    """Add an official status that replaces the latest one. The old one stays in the history."""
    f = _facility(db, facility_id)
    try:
        validate_for_facility_type(payload, f.type)
        user_row = evac_service.user_row_for(db, f.key)
        resolved = status_service.resolve_status(
            payload,
            status_service.effective_max_capacity(db, f.id, user_row.max_capacity if user_row else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    before = status_service.latest_row(db, f.id)
    row = StatusUpdate(
        facility_id=f.id,
        status=resolved.status,
        people_inside=resolved.people_inside,
        max_capacity=resolved.max_capacity,
        resources=json.dumps(payload.resources) if payload.resources else None,
        note=payload.note,
        source=status_service.OFFICIAL, kind=status_service.OVERRIDE, changed_by=user.name,
    )
    db.add(row)
    audit.record(
        db, user, "status.override", target=_target(f),
        detail={
            "from_status": before.status if before else None, "to_status": resolved.status,
            "people_inside": resolved.people_inside, "max_capacity": resolved.max_capacity,
            "reason": payload.reason,
        },
        request=request,
    )
    db.commit()
    db.refresh(row)
    out = status_service.to_status_out(row)
    out.message = resolved.message
    return out


def correct_capacity(
    db: Session, user: User, facility_id: int, payload: CapacityCorrectionIn, request: Optional[Request]
) -> FacilityOut:
    """Set the maximum capacity of an evacuation center. Needs a status to sit on (422 otherwise)."""
    f = _facility(db, facility_id)
    if f.type != evac_service.EVAC_TYPE:
        raise HTTPException(status_code=422, detail="Only evacuation centers have a maximum capacity.")
    latest = status_service.latest_row(db, f.id)
    if latest is None:
        raise HTTPException(
            status_code=422,
            detail="This center has no status yet. Override its status and send the capacity together with it.",
        )
    new = payload.max_capacity
    if status_service.official_max_capacity(db, f.id) == new:  # already the official number: nothing to do
        return evac_service.facility_out_for(db, f)
    if latest.people_inside is not None and latest.people_inside > new * OVERCROWD_FACTOR:
        raise HTTPException(
            status_code=422,
            detail=f"People inside ({latest.people_inside}) is far higher than {new}. Please check the number.",
        )

    user_row = evac_service.user_row_for(db, f.key)
    before = status_service.effective_max_capacity(db, f.id, user_row.max_capacity if user_row else None)
    row = StatusUpdate(
        facility_id=f.id, status=latest.status, people_inside=latest.people_inside, max_capacity=new,
        resources=latest.resources, note=None,
        source=status_service.OFFICIAL, kind=status_service.CAPACITY, changed_by=user.name,
    )
    db.add(row)
    audit.record(
        db, user, "capacity.correct", target=_target(f),
        detail={"from": before, "to": new, "reason": payload.reason}, request=request,
    )
    db.commit()
    return evac_service.facility_out_for(db, f)
