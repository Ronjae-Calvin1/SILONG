"""
Weather, advisories, official sources and emergency numbers (redesign part 4).

    GET    /api/weather                              public                 Batangas City forecast (cached; last good one if Open-Meteo is down)
    GET    /api/advisories                           public                 pinned first, then newest. ?official=true for official sources only
    POST   /api/admin/advisories                     super_admin            body: title, details, organization, source_url, pinned
    PATCH  /api/admin/advisories/{id}                super_admin            change any of title, details, organization, source_url
    POST   /api/admin/advisories/{id}/pin            super_admin
    POST   /api/admin/advisories/{id}/unpin          super_admin
    DELETE /api/admin/advisories/{id}                super_admin
    GET    /api/admin/advisory-sources               super_admin            the list of sources that count as official
    POST   /api/admin/advisory-sources               super_admin            body: name
    PATCH  /api/admin/advisory-sources/{id}          super_admin            body: name
    DELETE /api/admin/advisory-sources/{id}          super_admin
    GET    /api/emergency-numbers                    public                 in the order to show them
    POST   /api/admin/emergency-numbers              super_admin            body: number, name, description
    PATCH  /api/admin/emergency-numbers/{id}         super_admin
    DELETE /api/admin/emergency-numbers/{id}         super_admin
    PUT    /api/admin/emergency-numbers/order        super_admin            body: ids (every id, in the new order)

Every admin change is written to the audit log with the person's name. Nothing is fetched
automatically: advisories exist only because a Super admin posted them.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from . import content_service, weather_service
from .auth import require_super_admin
from .content_schemas import (
    AdvisoryIn, AdvisoryOut, AdvisorySourceIn, AdvisorySourceOut, AdvisoryUpdateIn,
    EmergencyNumberIn, EmergencyNumberOut, EmergencyNumberUpdateIn, EmergencyOrderIn, WeatherOut,
    advisory_out, number_out, source_out,
)
from .database import get_db
from .models import User

router = APIRouter(tags=["weather, advisories, emergency numbers"])


# ---- Weather ----

@router.get("/api/weather", response_model=WeatherOut)
def get_weather(db: Session = Depends(get_db)):
    """
    The forecast for Batangas City. `is_stale` is true (with a plain-language `notice`) when
    Open-Meteo could not be reached and this is the last good forecast; `fetched_at` says when it was
    received. 503 with a plain message when there has never been a good forecast.
    """
    return weather_service.get_weather(db)


# ---- Advisories: public ----

@router.get("/api/advisories", response_model=List[AdvisoryOut])
def list_advisories(
    official: Optional[bool] = Query(None, description="true = only advisories from official sources (the Warnings tab)"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Pinned first, then newest first. `is_official` is true when the organization is on the official list."""
    return [advisory_out(a, is_official) for a, is_official in content_service.list_advisories(db, bool(official), limit)]


# ---- Advisories: Super admin ----

@router.post("/api/admin/advisories", response_model=AdvisoryOut, status_code=201)
def create_advisory(payload: AdvisoryIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return advisory_out(*content_service.create_advisory(db, user, payload, request))


@router.patch("/api/admin/advisories/{advisory_id}", response_model=AdvisoryOut)
def update_advisory(advisory_id: int, payload: AdvisoryUpdateIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return advisory_out(*content_service.update_advisory(db, user, advisory_id, payload, request))


@router.post("/api/admin/advisories/{advisory_id}/pin", response_model=AdvisoryOut)
def pin_advisory(advisory_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Safe to call twice."""
    return advisory_out(*content_service.set_pinned(db, user, advisory_id, True, request))


@router.post("/api/admin/advisories/{advisory_id}/unpin", response_model=AdvisoryOut)
def unpin_advisory(advisory_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Safe to call twice."""
    return advisory_out(*content_service.set_pinned(db, user, advisory_id, False, request))


@router.delete("/api/admin/advisories/{advisory_id}", status_code=204)
def delete_advisory(advisory_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    content_service.delete_advisory(db, user, advisory_id, request)
    return Response(status_code=204)


# ---- Official sources: Super admin ----

@router.get("/api/admin/advisory-sources", response_model=List[AdvisorySourceOut])
def list_sources(user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """The names that count as official. Starts with PAGASA, NDRRMC and Batangas City CDRRMO."""
    return [source_out(s) for s in content_service.list_sources(db)]


@router.post("/api/admin/advisory-sources", response_model=AdvisorySourceOut, status_code=201)
def add_source(payload: AdvisorySourceIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return source_out(content_service.add_source(db, user, payload.name, request))


@router.patch("/api/admin/advisory-sources/{source_id}", response_model=AdvisorySourceOut)
def rename_source(source_id: int, payload: AdvisorySourceIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return source_out(content_service.rename_source(db, user, source_id, payload.name, request))


@router.delete("/api/admin/advisory-sources/{source_id}", status_code=204)
def remove_source(source_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Advisories from this source stay, but no longer show as official."""
    content_service.remove_source(db, user, source_id, request)
    return Response(status_code=204)


# ---- Emergency numbers ----

@router.get("/api/emergency-numbers", response_model=List[EmergencyNumberOut])
def list_numbers(db: Session = Depends(get_db)):
    """In the order to show them. Only 911 until the Batangas City CDRRMO confirms the others."""
    return [number_out(n) for n in content_service.list_numbers(db)]


@router.post("/api/admin/emergency-numbers", response_model=EmergencyNumberOut, status_code=201)
def add_number(payload: EmergencyNumberIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return number_out(content_service.add_number(db, user, payload, request))


# Declared before the {number_id} routes so that "order" is never read as an id.
@router.put("/api/admin/emergency-numbers/order", response_model=List[EmergencyNumberOut])
def reorder_numbers(payload: EmergencyOrderIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Send every id once, in the order to show them."""
    return [number_out(n) for n in content_service.reorder_numbers(db, user, payload.ids, request)]


@router.patch("/api/admin/emergency-numbers/{number_id}", response_model=EmergencyNumberOut)
def update_number(number_id: int, payload: EmergencyNumberUpdateIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return number_out(content_service.update_number(db, user, number_id, payload, request))


@router.delete("/api/admin/emergency-numbers/{number_id}", status_code=204)
def remove_number(number_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    content_service.remove_number(db, user, number_id, request)
    return Response(status_code=204)
