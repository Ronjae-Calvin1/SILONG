"""Request/response shapes for sign in, /api/me, Admin accounts and the audit log."""
import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import accounts, config
from .models import AuditLog, User


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Times are stored as naive UTC; send them out marked as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt is not None else None


class SignInIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=100)
    password: str = Field(max_length=accounts.PASSWORD_MAX)


class MeOut(BaseModel):
    id: int
    name: str
    role: Literal["admin"]  # always "admin": there is one role
    idle_timeout_minutes: int


class SignInOut(BaseModel):
    token: str  # send it back as `Authorization: Bearer <token>`
    token_type: str = "bearer"
    user: MeOut


class MessageOut(BaseModel):
    message: str


class UserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=100)
    password: str = Field(max_length=accounts.PASSWORD_MAX)
    # LEGACY, ignored. There is one role, so every new account is an Admin whatever is sent here. Still
    # accepted for ONE release so screens built for the old roles keep working; it will be rejected
    # (extra field) after that. Leave it out. Anything but "admin", "responder" or "super_admin" is a 422.
    role: Optional[Literal["admin", "responder", "super_admin"]] = Field(default=None, description="Deprecated and ignored: every account is an Admin. Accepted for one release.")


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(max_length=accounts.PASSWORD_MAX)
    new_password: str = Field(max_length=accounts.PASSWORD_MAX)  # same minimum length as account creation


class ResetPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(max_length=accounts.PASSWORD_MAX)  # typed by the Admin; never sent back


class BlockedPhoneOut(BaseModel):
    """A blocked phone. There is no phone ID and no hash here, on purpose."""
    id: int
    blocked_at: datetime
    false_reports: int  # how many false reports it had when it was blocked
    expires_at: Optional[datetime] = None  # null = the block never ends by itself (BLOCK_EXPIRES_DAYS=0)


class UserOut(BaseModel):
    id: int
    name: str
    role: Literal["admin"]  # always "admin": there is one role
    status: Literal["active", "locked_by_admin", "locked_for_wrong_tries"]
    locked_until: Optional[datetime] = None  # only while locked for wrong tries
    created_at: datetime
    created_by: Optional[str] = None
    last_sign_in_at: Optional[datetime] = None
    message: Optional[str] = None


class AuditEntryOut(BaseModel):
    id: int
    created_at: datetime
    actor_id: Optional[int] = None
    actor_name: str
    actor_role: Optional[str] = None
    action: str
    target: Optional[str] = None
    detail: Any = None


def me_out(user: User) -> MeOut:
    return MeOut(id=user.id, name=user.name, role=accounts.ADMIN, idle_timeout_minutes=config.STAFF_IDLE_MINUTES)


def user_out(user: User, message: Optional[str] = None) -> UserOut:
    now = accounts._now()
    wrong_tries_lock = user.locked_until is not None and user.locked_until > now
    status = "locked_by_admin" if user.is_locked else "locked_for_wrong_tries" if wrong_tries_lock else "active"
    return UserOut(
        id=user.id, name=user.name, role=accounts.ADMIN, status=status,
        locked_until=_utc(user.locked_until) if wrong_tries_lock else None,
        created_at=_utc(user.created_at), created_by=user.created_by,
        last_sign_in_at=_utc(user.last_sign_in_at), message=message,
    )


def blocked_phone_out(d: dict) -> BlockedPhoneOut:
    return BlockedPhoneOut(
        id=d["id"], blocked_at=_utc(d["blocked_at"]), false_reports=d["false_reports"], expires_at=_utc(d["expires_at"]),
    )


def audit_out(row: AuditLog) -> AuditEntryOut:
    try:
        detail = json.loads(row.detail) if row.detail else None
    except ValueError:
        detail = row.detail
    return AuditEntryOut(
        id=row.id, created_at=_utc(row.created_at), actor_id=row.actor_id, actor_name=row.actor_name,
        actor_role=row.actor_role, action=row.action, target=row.target, detail=detail,
    )
