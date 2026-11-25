"""
Contact settings (update 14).

    GET   /api/support-contact          public   support email and number for the Contact screen (null = not set)
    GET   /api/admin/contact-settings   admin    control-room number, support email and number
    PATCH /api/admin/contact-settings   admin    change any of the three (null clears); audited

The control-room number is never in a public answer.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from . import settings_service
from .auth import require_admin
from .database import get_db
from .models import User
from .settings_schemas import ContactSettingsIn, ContactSettingsOut, SupportContactOut

router = APIRouter(tags=["contact settings"])


@router.get("/api/support-contact", response_model=SupportContactOut)
def support_contact(db: Session = Depends(get_db)):
    """Support email and number for the Contact screen. A value that is not set is null: show nothing, not a placeholder."""
    return settings_service.support_contact(db)


@router.get("/api/admin/contact-settings", response_model=ContactSettingsOut)
def get_contact_settings(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """The control-room number (for the Me screen's call button) and the support contact. null = not set."""
    return settings_service.contact_settings(db)


@router.patch("/api/admin/contact-settings", response_model=ContactSettingsOut)
def update_contact_settings(
    payload: ContactSettingsIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Send only the fields to change. null or an empty text clears one. A change is audited with the Admin's name."""
    return settings_service.update_contact_settings(db, user, payload, request)
