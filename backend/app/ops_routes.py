"""
Phone blocks (redesign part 5). Super admin only. Every change is audited with the person's name.

    GET  /api/admin/blocked-phones                 super_admin   phones blocked after false reports
    POST /api/admin/blocked-phones/{id}/unblock    super_admin   let a phone send reports again

A phone is blocked after FALSE_REPORTS_BEFORE_BLOCK false reports (report_service.mark_false). The
list shows the row number, the date and the count only: never the phone ID or its hash. A block can
also end by itself after BLOCK_EXPIRES_DAYS days (0, the default, = never).
"""
from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from . import report_service
from .account_schemas import BlockedPhoneOut, MessageOut, blocked_phone_out
from .auth import require_super_admin
from .database import get_db
from .models import User

router = APIRouter(tags=["phone blocks"])


@router.get("/api/admin/blocked-phones", response_model=List[BlockedPhoneOut])
def list_blocked_phones(user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Blocked phones, newest first. `expires_at` is null when blocks never expire."""
    return [blocked_phone_out(d) for d in report_service.list_blocked_phones(db)]


@router.post("/api/admin/blocked-phones/{block_id}/unblock", response_model=MessageOut)
def unblock_phone(block_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """
    Let this phone send reports again. Its count of false reports starts from zero, so it takes
    a fresh set of false reports to block it again.
    """
    report_service.unblock_phone(db, user, block_id, request)
    return MessageOut(message="The phone can send reports again.")
