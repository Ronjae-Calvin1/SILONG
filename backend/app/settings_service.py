"""
Contact settings: the control-room number (Admins only), and the support email and number (public, for the
Contact screen). Stored in app_settings; a value that was never set, or was cleared, has no row and comes back
as null (never placeholder text). Every change is audited with the person's name and committed with the change.
"""
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import audit
from .models import AppSetting, User
from .settings_schemas import ContactSettingsOut, SupportContactOut, _utc

CONTROL_ROOM, SUPPORT_EMAIL, SUPPORT_NUMBER = "control_room_number", "support_email", "support_number"
KEYS = (CONTROL_ROOM, SUPPORT_EMAIL, SUPPORT_NUMBER)


def _rows(db: Session) -> Dict[str, AppSetting]:
    return {r.key: r for r in db.query(AppSetting).filter(AppSetting.key.in_(KEYS)).all()}


def support_contact(db: Session) -> SupportContactOut:
    rows = _rows(db)
    return SupportContactOut(
        support_email=rows[SUPPORT_EMAIL].value if SUPPORT_EMAIL in rows else None,
        support_number=rows[SUPPORT_NUMBER].value if SUPPORT_NUMBER in rows else None,
    )


def contact_settings(db: Session) -> ContactSettingsOut:
    rows = _rows(db)
    latest = max(rows.values(), key=lambda r: r.updated_at) if rows else None
    return ContactSettingsOut(
        control_room_number=rows[CONTROL_ROOM].value if CONTROL_ROOM in rows else None,
        support_email=rows[SUPPORT_EMAIL].value if SUPPORT_EMAIL in rows else None,
        support_number=rows[SUPPORT_NUMBER].value if SUPPORT_NUMBER in rows else None,
        updated_at=_utc(latest.updated_at) if latest else None,
        updated_by=latest.updated_by if latest else None,
    )


def update_contact_settings(db: Session, user: User, payload, request: Optional[Request]) -> ContactSettingsOut:
    rows = _rows(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    changed, was = [], {}
    for key in KEYS:
        if key not in payload.model_fields_set:
            continue
        new = getattr(payload, key)
        old = rows[key].value if key in rows else None
        if new == old:
            continue
        changed.append(key)
        was[key] = old
        if new is None:
            db.delete(rows[key])
        elif key in rows:
            rows[key].value, rows[key].updated_at, rows[key].updated_by = new, now, user.name
        else:
            db.add(AppSetting(key=key, value=new, updated_at=now, updated_by=user.name))
    if changed:
        audit.record(db, user, "settings.contact_update", target="contact_settings",
                     detail={"changed": changed, "was": was}, request=request)
        db.commit()
    return contact_settings(db)
