"""
Admin endpoints for places and statuses (part 3). Every change is audited with the person's name.

    GET    /api/admin/places                           admin   places waiting for approval (?status=rejected for rejected ones)
    POST   /api/admin/places/{id}/approve              admin   make a place public
    POST   /api/admin/places/{id}/reject               admin   body (optional): reason
    PATCH  /api/admin/places/{id}                      admin   correct name, address, barangay, contact, note
    DELETE /api/admin/places/{id}                      admin   delete a removed center or rejected place for good, now
    POST   /api/admin/facilities/{id}/status-override      admin   replace the latest status
    POST   /api/admin/facilities/{id}/capacity-correction  admin   correct the maximum capacity
    GET    /api/admin/facilities/{id}/status-history       admin   the full history with names

Removing and restoring a center, and the list of removed centers, stay on /api/evacuation-centers
(evac_routes.py), for Admins only.
"""
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from . import place_service, status_admin, status_service
from .auth import require_admin
from .database import get_db
from .models import Facility, User
from .schemas import (
    AdminStatusOut, CapacityCorrectionIn, FacilityOut, PlaceAdminOut, PlaceEditIn, RejectIn, StatusOut, StatusOverrideIn,
)

router = APIRouter(tags=["places (admin)"])


@router.get("/api/admin/places", response_model=List[PlaceAdminOut])
def list_places(
    status: Literal["pending", "rejected"] = Query("pending", description="Which added places to list"),
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """
    Added places with their exact details. Pending ones (the default) are the queue to review,
    the longest-waiting first; each carries `possible_duplicate` when an existing center has the
    same name within 30 m.
    """
    return place_service.list_places(db, status)


@router.patch("/api/admin/places/{facility_id}", response_model=PlaceAdminOut)
def edit_place(
    facility_id: int, payload: PlaceEditIn, request: Request,
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """
    Correct the details of an evacuation center that was added through the app: send only the fields
    to change (name, address, barangay, contact, note). A new name that matches another center within
    30 m is refused (409). Centers from the map data files, hospitals and clinics cannot be edited (409).
    """
    return place_service.edit_center(db, user, facility_id, {k: getattr(payload, k) for k in payload.model_fields_set}, request)


@router.post("/api/admin/places/{facility_id}/approve", response_model=PlaceAdminOut)
def approve_place(facility_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Make a pending place public. Also undoes a rejection. Safe to call twice."""
    return place_service.approve(db, user, facility_id, request)


@router.post("/api/admin/places/{facility_id}/reject", response_model=PlaceAdminOut)
def reject_place(
    facility_id: int, request: Request, payload: RejectIn = RejectIn(),
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Reject a pending place (the reason is optional). A place already on the map is removed instead (409). Safe to call twice."""
    return place_service.reject(db, user, facility_id, payload.reason, request)


@router.delete("/api/admin/places/{facility_id}")
def delete_place_for_good(facility_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Delete a removed center, or a rejected place, together with its status history, now (instead of waiting for the purge)."""
    return place_service.delete_for_good(db, user, facility_id, request)


@router.post("/api/admin/facilities/{facility_id}/status-override", response_model=StatusOut, status_code=201)
def override_status(
    facility_id: int, payload: StatusOverrideIn, request: Request,
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """
    Replace the latest status. Same fields as a user report plus an optional `reason`. It is added to
    the history as "Confirmed by official" with your name; the status it replaces stays in the history.
    """
    return status_admin.override_status(db, user, facility_id, payload, request)


@router.post("/api/admin/facilities/{facility_id}/capacity-correction", response_model=FacilityOut)
def correct_capacity(
    facility_id: int, payload: CapacityCorrectionIn, request: Request,
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Correct the maximum capacity of an evacuation center. Added to the history; users cannot change it afterwards."""
    return status_admin.correct_capacity(db, user, facility_id, payload, request)


@router.get("/api/admin/facilities/{facility_id}/status-history", response_model=List[AdminStatusOut])
def admin_status_history(
    facility_id: int, limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Every row of the history, newest first, including overrides and capacity corrections, with staff names."""
    f = db.get(Facility, facility_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Facility not found.")
    return status_service.admin_history(db, facility_id, limit)
