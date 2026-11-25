"""
Admin accounts and sign in. One role, Admin: every route below that is not public needs a signed-in
Admin, and every Admin can use all of them.

    POST   /api/auth/sign-in               public (needs an Admin account)
    POST   /api/auth/sign-out              signed in
    POST   /api/auth/change-password       signed in
    GET    /api/me                         admin
    GET    /api/admin/users                admin
    POST   /api/admin/users                admin
    POST   /api/admin/users/{id}/lock      admin
    POST   /api/admin/users/{id}/unlock    admin
    POST   /api/admin/users/{id}/reset-password  admin
    DELETE /api/admin/users/{id}           admin
    GET    /api/admin/audit-log            admin

There is no public sign-up. Every change below is written to the audit log. You cannot lock or remove
yourself, and the last active Admin cannot be locked or removed.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import accounts, config
from .account_schemas import (
    AuditEntryOut, ChangePasswordIn, MeOut, MessageOut, ResetPasswordIn, SignInIn, SignInOut, UserCreateIn, UserOut,
    audit_out, me_out, user_out,
)
from .auth import bearer_token, current_user, require_admin
from .database import get_db
from .models import AuditLog, User
from .rate_limit import signin_limiter

router = APIRouter(tags=["accounts"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/api/auth/sign-in", response_model=SignInOut)
def sign_in(payload: SignInIn, request: Request, db: Session = Depends(get_db)):
    """Sign in with a name and password. Locked for 15 minutes after 5 wrong tries in a row."""
    wait = signin_limiter.check(_ip(request))
    if wait is not None:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many sign-in tries from your connection. Please try again in about {minutes} minute(s).",
            headers={"Retry-After": str(wait)},
        )
    token, user = accounts.sign_in(db, payload.name, payload.password, request)
    return SignInOut(token=token, user=me_out(user))


@router.post("/api/auth/sign-out", response_model=MessageOut)
def sign_out(request: Request, token: Optional[str] = Depends(bearer_token), db: Session = Depends(get_db)):
    """Ends this sign-in. Safe to call twice."""
    accounts.sign_out(db, token, request)
    return MessageOut(message="You are signed out.")


@router.post("/api/auth/change-password", response_model=MessageOut)
def change_password(
    payload: ChangePasswordIn, request: Request,
    token: Optional[str] = Depends(bearer_token), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """
    Change your own password. A wrong current password is refused (403) and counted toward a limit
    per person and per IP (429 when it is used up). Your other sign-ins end; this one stays.
    """
    ended = accounts.change_password(db, user, token, payload.current_password, payload.new_password, _ip(request), request)
    extra = f" You were signed out on {ended} other device(s)." if ended else ""
    return MessageOut(message="Your password was changed." + extra)


@router.get("/api/me", response_model=MeOut)
def me(user: User = Depends(require_admin)):
    """Who is signed in."""
    return me_out(user)


# ---- Admin: accounts ----

@router.get("/api/admin/users", response_model=List[UserOut])
def list_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/api/admin/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreateIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Create an Admin account. There is no public sign-up. `role` is a legacy field: it is ignored (every
    account is an Admin) and accepted for one release only; leave it out.
    """
    created = accounts.create_user(db, payload.name, payload.password, actor=user, request=request)
    note = "The role field is ignored: every account is an Admin." if payload.role is not None else None
    return user_out(created, note)


@router.post("/api/admin/users/{user_id}/lock", response_model=UserOut)
def lock_user(user_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Lock an account until an Admin unlocks it. The person is signed out right away. Not your own account, and not the last active Admin."""
    target = accounts.get_user_or_404(db, user_id)
    changed = accounts.lock_user(db, user, target, request)
    return user_out(target, None if changed else "This account was already locked.")


@router.post("/api/admin/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Unlock an account (also clears a lock from too many wrong tries)."""
    target = accounts.get_user_or_404(db, user_id)
    accounts.unlock_user(db, user, target, request)
    return user_out(target)


@router.post("/api/admin/users/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: int, payload: ResetPasswordIn, request: Request,
    user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """
    Set a new password for someone else (a forgotten password). The person is signed out everywhere and
    their wrong-try count and automatic lock are cleared. Tell them the new password yourself: it is
    never shown again. Not for your own account (use change-password).
    """
    target = accounts.get_user_or_404(db, user_id)
    ended = accounts.reset_password(db, user, target, payload.new_password, request)
    return user_out(target, f"The password for {target.name} was reset and they were signed out ({ended} sign-in(s) ended).")


@router.delete("/api/admin/users/{user_id}", response_model=MessageOut)
def remove_user(user_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Remove an account. Its audit entries are kept. Not your own account, and not the last active Admin."""
    target = accounts.get_user_or_404(db, user_id)
    name = target.name
    accounts.remove_user(db, user, target, request)
    return MessageOut(message=f"The account for {name} was removed.")


# ---- Admin: audit log ----

def _day(value: Optional[str], label: str) -> Optional[datetime]:
    """A YYYY-MM-DD date (UTC, like every time here) as the start of that day, or a plain 422."""
    if value is None or value.strip() == "":
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail=f'The "{label}" date must look like 2026-11-30 (year-month-day).')


@router.get(
    "/api/admin/audit-log", response_model=List[AuditEntryOut],
    responses={200: {"description": "The matching entries, newest first.", "headers": {
        "X-Total-Count": {"description": "How many entries match the filters, before limit and offset.", "schema": {"type": "integer"}},
    }}},
)
def read_audit_log(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, description="Paging: skip this many entries (newest first)"),
    before_id: Optional[int] = Query(None, ge=1, description="Paging: only entries older than this id"),
    action: Optional[str] = Query(None, max_length=60, description="Only this action, e.g. user.create"),
    actor: Optional[str] = Query(None, max_length=100, description="Only this exact person's name"),
    person: Optional[str] = Query(None, max_length=100, description="Name search: part of a name, any capitals"),
    date_from: Optional[str] = Query(None, alias="from", description="First day to include, YYYY-MM-DD (UTC)"),
    date_to: Optional[str] = Query(None, alias="to", description="Last day to include, YYYY-MM-DD (UTC)"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Newest first. The body is the same list as before; the number of entries that match the filters
    (before limit and offset) is in the X-Total-Count response header.
    """
    start, end = _day(date_from, "from"), _day(date_to, "to")
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail='The "from" date must not be later than the "to" date.')
    q = db.query(AuditLog)
    if before_id is not None:
        q = q.filter(AuditLog.id < before_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor_name == actor.strip())
    if person and person.strip():
        q = q.filter(func.lower(AuditLog.actor_name).contains(person.strip().lower(), autoescape=True))
    if start is not None:
        q = q.filter(AuditLog.created_at >= start)
    if end is not None:
        q = q.filter(AuditLog.created_at < end + timedelta(days=1))
    response.headers["X-Total-Count"] = str(q.count())
    return [audit_out(r) for r in q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()]
