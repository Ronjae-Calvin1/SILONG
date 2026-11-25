"""
Admin console helpers (update 14).

    GET /api/admin/summary       admin   the badge numbers in one cheap call
    GET /api/admin/me/activity   admin   the signed-in Admin's recent actions and "handled N reports today"

Read only: nothing here changes data, so nothing is written to the audit log.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from . import console_service
from .auth import require_admin
from .console_schemas import MyActivityOut, SummaryOut, activity_item_out, utc
from .database import get_db
from .models import User

router = APIRouter(tags=["admin console"])


@router.get("/api/admin/summary", response_model=SummaryOut)
def admin_summary(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    The numbers for the tab and chip badges, in one call (a few COUNT queries, no lists): new reports,
    being handled, mine, places waiting for approval, removed centers. Poll it with the report list.
    """
    data = console_service.summary(db, user)
    data["server_time"] = utc(data["server_time"])
    return SummaryOut(**data)


@router.get("/api/admin/me/activity", response_model=MyActivityOut)
def my_activity(
    limit: int = Query(20, ge=1, le=100, description="How many recent actions to list"),
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """
    The signed-in Admin's own recent actions from the audit log (newest first, sign-ins left out) and how many
    different reports they handled today. Only your own actions are ever returned.
    """
    data = console_service.my_activity(db, user, limit)
    return MyActivityOut(
        server_time=utc(data["server_time"]), today_starts_at=utc(data["today_starts_at"]),
        handled_today=data["handled_today"], items=[activity_item_out(r) for r in data["items"]],
    )
