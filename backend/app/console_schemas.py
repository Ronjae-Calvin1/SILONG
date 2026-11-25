"""Request/response shapes for the Admin console helpers (badge counts, my recent actions)."""
import json
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel


class SummaryOut(BaseModel):
    """The badge numbers for the Admin screens. Open reports only; a hazard counts once for all its reports."""
    server_time: datetime
    new_reports: int  # status New (help requests and hazards): the Reports badge
    being_handled: int  # status Being handled, by anyone
    mine: int  # Being handled by the signed-in Admin
    pending_places: int  # places waiting for approval: the Places badge
    removed_centers: int  # centers removed and still kept (not yet deleted for good)


class ActivityItemOut(BaseModel):
    id: int
    created_at: datetime  # UTC
    action: str  # e.g. report.resolve, place.approve
    target: Optional[str] = None  # e.g. "report:12"
    detail: Optional[Any] = None  # what was entered, as JSON (reasons and notes the Admin typed; never a phone ID)


class MyActivityOut(BaseModel):
    server_time: datetime
    handled_today: int  # different reports this Admin took (and kept), resolved, marked false or verified today
    today_starts_at: datetime  # UTC moment "today" began (local midnight, see ADMIN_DAY_UTC_OFFSET_HOURS)
    items: List[ActivityItemOut]  # newest first; sign-ins and sign-outs are not listed


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc)


def activity_item_out(row) -> ActivityItemOut:
    try:
        detail = json.loads(row.detail) if row.detail else None
    except ValueError:
        detail = None
    return ActivityItemOut(id=row.id, created_at=utc(row.created_at), action=row.action, target=row.target, detail=detail)
