"""
Help requests and hazard reports.

    POST /api/reports                          public, X-Phone-Id   send a help request or a hazard
    GET  /api/reports/mine                     public, X-Phone-Id   this phone's own reports and their status
    GET  /api/hazards/nearby                   public               hazards within the near-me range (approximate spot)
    GET  /api/admin/reports                    admin                list for the Admin screens (poll ~10 s; ?status, ?mine, ?latitude&longitude, ?since)
    POST /api/admin/reports/{id}/take          admin                also takes over a report another Admin is handling
    POST /api/admin/reports/{id}/release       admin                give any open report back to New (yours or another Admin's)
    POST /api/admin/reports/{id}/resolve       admin                body: what_was_done
    POST /api/admin/reports/{id}/mark-false    admin                body: reason
    POST /api/admin/reports/{id}/verify        admin                hazards only

The public endpoints have no sign-in: the protection is the phone ID, the
per-phone and per-IP limits (rate_limit.py) and the block after false reports.
Admin actions are audited (audit.py).
"""
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from . import report_service
from .auth import require_admin
from .database import get_db
from .models import User
from .rate_limit import read_limiter, report_limiter
from .report_schemas import (
    MarkFalseIn, MyReportOut, NearbyHazardOut, ReportIn, ReportSentOut, ResolveIn,
    AdminListOut, AdminReportOut, admin_item_out, admin_list_out, my_report_out,
)

router = APIRouter(tags=["reports"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def required_phone(x_phone_id: Optional[str] = Header(default=None)) -> str:
    """The hashed phone ID from the X-Phone-Id header. 400 when it is missing or malformed."""
    return report_service.phone_hash_from_header(x_phone_id, required=True)


def optional_phone(x_phone_id: Optional[str] = Header(default=None)) -> Optional[str]:
    return report_service.phone_hash_from_header(x_phone_id, required=False)


def _read_limit(request: Request, phone: Optional[str]) -> None:
    wait = read_limiter.check(_ip(request), phone)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Please try again in {wait} second(s).",
            headers={"Retry-After": str(wait)},
        )


# ---- Public ----

@router.post("/api/reports", response_model=ReportSentOut, status_code=201)
def send_report(
    payload: ReportIn, request: Request, response: Response,
    phone: str = Depends(required_phone), db: Session = Depends(get_db),
):
    """
    Send a help request ("kind": "help") or a hazard report ("kind": "hazard"). Both need a
    `category`; a help request also needs a `contact` and may have `people` and `can_move`
    (not allowed on a hazard). Field rules are in ReportIn.
    """
    if report_service.is_blocked(db, phone):
        raise HTTPException(
            status_code=403,
            detail="This phone can no longer send reports, because several of its reports were marked false. "
                   "In an emergency, call 911.",
        )
    # Limits after validation (the body is already checked) and the block, so a mistake does not use up the allowance.
    hit = report_limiter.check(_ip(request), phone, payload.kind)
    if hit:
        scope, wait = hit
        if scope == "cooldown":
            msg = f"You just sent a report. Please wait {wait} seconds before sending another one."
        else:
            minutes = max(1, round(wait / 60))
            msg = ("Too many reports from this phone." if scope == "phone" else "Too many reports from your connection.")
            msg += f" Please try again in about {minutes} minute(s). In an emergency, call 911."
        raise HTTPException(status_code=429, detail=msg, headers={"Retry-After": str(wait)})

    row, created = report_service.create_report(
        db, payload.kind, payload.latitude, payload.longitude, payload.contact, payload.note, phone, _ip(request),
        category=payload.category, people=payload.people, can_move=payload.can_move,
    )
    db.commit()
    db.refresh(row)
    if not created:
        response.status_code = 200
    status = report_service.PUBLIC_STATUS[row.status]
    if payload.kind == report_service.HELP:
        message = "Your request was sent to the Admins. If it is an emergency, also call 911."
    elif created:
        message = "Thank you. Your hazard report was received."
    else:
        message = "You already reported this hazard. Thank you."
    return ReportSentOut(
        id=row.id, kind=row.kind, status=status, label=report_service.PUBLIC_LABEL[status],
        created_at=row.created_at.replace(tzinfo=timezone.utc), message=message,
    )


@router.get("/api/reports/mine", response_model=List[MyReportOut])
def my_reports(request: Request, phone: str = Depends(required_phone), db: Session = Depends(get_db)):
    """This phone's own reports, newest first, with a status: New, Being handled or Resolved."""
    _read_limit(request, phone)
    return [my_report_out(d) for d in report_service.reports_of_phone(db, phone)]


@router.get("/api/hazards/nearby", response_model=List[NearbyHazardOut])
def nearby_hazards(
    request: Request,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    phone: Optional[str] = Depends(optional_phone),
    db: Session = Depends(get_db),
):
    """
    Hazards within the near-me range (config.NEAR_ME_KM) that are Unconfirmed or
    Verified, as an approximate spot with a status and no details. The position
    you send is used for this answer only and is not stored.
    """
    _read_limit(request, phone)
    return [NearbyHazardOut(**h) for h in report_service.nearby_hazards(db, latitude, longitude)]


# ---- Admins ----

@router.get("/api/admin/reports", response_model=AdminListOut)
def admin_reports(
    include_closed: bool = Query(False, description="Also list resolved and false reports"),
    status: Optional[Literal["new", "handling", "resolved", "all"]] = Query(
        None, description="Only this status: new, handling, resolved (closed: resolved and false) or all (open and closed). Not given: open reports"),
    kind: Optional[Literal["help", "hazard"]] = Query(None),
    mine: bool = Query(False, description="Only reports you took (the Mine filter)"),
    latitude: Optional[float] = Query(None, ge=-90, le=90, description="With longitude: add distance_m to each item"),
    longitude: Optional[float] = Query(None, ge=-180, le=180, description="With latitude: add distance_m to each item"),
    since: Optional[datetime] = Query(None, description="Only items that changed at or after this time (ISO 8601; no zone = UTC). Use the last server_time"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Poll this about every `refresh_seconds` (10). `has_new_help` is true while
    any help request is still New: show the red "Needs help" alert. Open reports
    only, unless include_closed is set. A hazard is one line for all reports
    about the same place.

    `status` (new, handling, resolved, all) lists only that status; `resolved` includes reports marked false and `all`
    includes closed ones. Not given, you get the open reports (or everything with `include_closed`). When `status` is
    given it decides, and `include_closed` adds nothing. It combines with `mine`, `kind`, `since` and the distance.

    `mine=true` keeps only the reports you took. Send `latitude` and `longitude` together to get
    `distance_m` on every item (the order stays most urgent first). For polling, send the last answer's
    `server_time` as `since`: you get only the items that changed since, and that includes reports that were
    just resolved or marked false, so you can drop them from your list. `new_help_count`, `has_new_help`
    and `latest_report_id` always cover everything.
    """
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Send latitude and longitude together, or neither.")
    if since is not None and since.tzinfo is not None:
        since = since.astimezone(timezone.utc).replace(tzinfo=None)  # stored times are naive UTC
    data = report_service.admin_list(
        db, include_closed=include_closed, kind=kind, viewer=user.name, mine=mine,
        lat=latitude, lng=longitude, since=since, status=status,
    )
    data["since"] = since
    return admin_list_out(data)


@router.post("/api/admin/reports/{report_id}/take", response_model=AdminReportOut)
def take_report(report_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Take it: New -> Being handled. If another Admin has it, you take it over (it is reassigned to you). 409 only if it is closed. Safe to call twice."""
    return admin_item_out(report_service.take(db, user, report_id, request))


@router.post("/api/admin/reports/{report_id}/release", response_model=AdminReportOut)
def release_report(report_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Give a report back: Being handled -> New, nobody assigned. Any Admin can, also for one another Admin took. 409 only if it is closed. Safe to call twice."""
    return admin_item_out(report_service.release(db, user, report_id, request))


@router.post("/api/admin/reports/{report_id}/resolve", response_model=AdminReportOut)
def resolve_report(report_id: int, payload: ResolveIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Resolve. Needs `what_was_done`. The sender then sees Resolved."""
    return admin_item_out(report_service.resolve(db, user, report_id, payload.what_was_done, request))


@router.post("/api/admin/reports/{report_id}/mark-false", response_model=AdminReportOut)
def mark_report_false(report_id: int, payload: MarkFalseIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Mark false. Needs a `reason`. A phone with 3 false reports is blocked from sending reports."""
    return admin_item_out(report_service.mark_false(db, user, report_id, payload.reason, request))


@router.post("/api/admin/reports/{report_id}/verify", response_model=AdminReportOut)
def verify_report(report_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Verify a hazard: the public then sees it as Verified. Hazards only. Safe to call twice."""
    return admin_item_out(report_service.verify(db, user, report_id, request))
