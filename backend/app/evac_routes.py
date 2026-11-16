"""
Evacuation center manager endpoints.

    POST   /api/evacuation-centers                public, X-Phone-Id (optional)   add a place: it starts as PENDING
    GET    /api/evacuation-centers/removed        responder, super_admin          centers removed for everyone
    DELETE /api/evacuation-centers/{id}           responder, super_admin          remove a center for everyone
    POST   /api/evacuation-centers/{id}/restore   responder, super_admin          bring a removed center back

Approving, rejecting and deleting for good are in place_routes.py.

Adding is the only public action here. The place is visible only to the phone that sent it (the
hashed X-Phone-Id, handled like in the reports) until a responder or Super admin approves it.
Removing is a staff action and affects everybody; "Hide on this phone" is done in the browser and
never reaches the server. Nothing here deletes a row: the purge does that after
config.REMOVED_CENTERS_KEEP_DAYS days (place_service.py).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config, evac_service, place_service
from .auth import require_responder
from .database import get_db
from .models import User
from .rate_limit import manage_limiter
from .report_routes import optional_phone
from .schemas import EvacCenterIn, FacilityOut, RemovalOut

router = APIRouter(prefix="/api/evacuation-centers", tags=["evacuation centers"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit(request: Request, phone: Optional[str]) -> None:
    """429 when this IP (or this phone) has used up its allowance for adding places."""
    for who in (_ip(request), f"phone:{phone}" if phone else None):
        if who is None:
            continue
        wait = manage_limiter.check(who)
        if wait is not None:
            minutes = max(1, round(wait / 60))
            raise HTTPException(
                status_code=429,
                detail=f"Too many changes from your connection. Please try again in about {minutes} minute(s).",
                headers={"Retry-After": str(wait)},
            )


@router.post("", response_model=FacilityOut, status_code=201)
def add_center(
    payload: EvacCenterIn, request: Request,
    phone: Optional[str] = Depends(optional_phone), db: Session = Depends(get_db),
):
    """
    Add an evacuation center. Field rules live in schemas.EvacCenterIn. The place starts as
    PENDING ("approval_status": "pending"): you see it, nobody else does, until a responder or
    Super admin approves it. Send the X-Phone-Id header (the same one the reports use), or you will
    not see it again after a reload. A possible duplicate (same name within 30 m) does not stop
    the place: it is flagged for the responder who reviews it.
    """
    if phone:
        if evac_service.pending_duplicate_of_phone(db, phone, payload.name, payload.latitude, payload.longitude):
            raise HTTPException(
                status_code=409,
                detail="You already added this place. It is waiting for approval by a responder.",
            )
        if evac_service.pending_count_of_phone(db, phone) >= config.PENDING_PLACES_PER_PHONE:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You already have {config.PENDING_PLACES_PER_PHONE} places waiting for approval. "
                    "Please wait until a responder has looked at them."
                ),
            )
    # Limit after validation and the checks above, so a mistake does not use up the allowance.
    _limit(request, phone)

    facility = evac_service.create_center(db, payload, phone_hash=phone)
    evac_service.log_action(db, "add", facility.key, _ip(request))
    db.commit()
    db.refresh(facility)
    return evac_service.facility_out_for(db, facility)


@router.get("/removed", response_model=List[RemovalOut])
def list_removed(user: User = Depends(require_responder), db: Session = Depends(get_db)):
    """Centers that are removed right now, newest first, each with the day it will be deleted for good."""
    return place_service.list_removed(db)


@router.delete("/{facility_id}", response_model=RemovalOut)
def remove_center(
    facility_id: int, request: Request,
    user: User = Depends(require_responder), db: Session = Depends(get_db),
):
    """Remove a center for everyone. Its data and status history are kept (30 days) so it can be restored."""
    return place_service.remove(db, user, facility_id, request)


@router.post("/{facility_id}/restore", response_model=FacilityOut)
def restore_center(
    facility_id: int, request: Request,
    user: User = Depends(require_responder), db: Session = Depends(get_db),
):
    """Bring a removed center back on the map."""
    facility = place_service.restore(db, user, facility_id, request)
    return evac_service.facility_out_for(db, facility)
