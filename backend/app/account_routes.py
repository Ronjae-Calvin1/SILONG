"""
Staff accounts and sign in.

    POST   /api/auth/sign-in               public (needs a staff account)
    POST   /api/auth/sign-out              signed in
    GET    /api/me                         responder, super_admin
    GET    /api/admin/users                super_admin
    POST   /api/admin/users                super_admin
    POST   /api/admin/users/{id}/lock      super_admin
    POST   /api/admin/users/{id}/unlock    super_admin
    DELETE /api/admin/users/{id}           super_admin
    GET    /api/admin/audit-log            super_admin

There is no public sign-up. Every change below is written to the audit log.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from . import accounts, config
from .account_schemas import (
    AuditEntryOut, MeOut, MessageOut, SignInIn, SignInOut, UserCreateIn, UserOut,
    audit_out, me_out, user_out,
)
from .auth import bearer_token, require_responder, require_super_admin
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


@router.get("/api/me", response_model=MeOut)
def me(user: User = Depends(require_responder)):
    """Who is signed in. Any staff role."""
    return me_out(user)


# ---- Super admin: accounts ----

@router.get("/api/admin/users", response_model=List[UserOut])
def list_users(user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/api/admin/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreateIn, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Create a responder or Super admin account. There is no public sign-up."""
    created = accounts.create_user(db, payload.name, payload.password, payload.role, actor=user, request=request)
    return user_out(created)


@router.post("/api/admin/users/{user_id}/lock", response_model=UserOut)
def lock_user(user_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Lock an account until a Super admin unlocks it. The person is signed out right away."""
    target = accounts.get_user_or_404(db, user_id)
    changed = accounts.lock_user(db, user, target, request)
    return user_out(target, None if changed else "This account was already locked.")


@router.post("/api/admin/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Unlock an account (also clears a lock from too many wrong tries)."""
    target = accounts.get_user_or_404(db, user_id)
    accounts.unlock_user(db, user, target, request)
    return user_out(target)


@router.delete("/api/admin/users/{user_id}", response_model=MessageOut)
def remove_user(user_id: int, request: Request, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Remove an account. Its audit entries are kept."""
    target = accounts.get_user_or_404(db, user_id)
    name = target.name
    accounts.remove_user(db, user, target, request)
    return MessageOut(message=f"The account for {name} was removed.")


# ---- Super admin: audit log ----

@router.get("/api/admin/audit-log", response_model=List[AuditEntryOut])
def read_audit_log(
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = Query(None, ge=1, description="Paging: only entries older than this id"),
    action: Optional[str] = Query(None, max_length=60, description="Only this action, e.g. user.create"),
    actor: Optional[str] = Query(None, max_length=100, description="Only this person's name"),
    user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Newest first. Use before_id (the last id you got) to load the next page."""
    q = db.query(AuditLog)
    if before_id is not None:
        q = q.filter(AuditLog.id < before_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor_name == actor.strip())
    return [audit_out(r) for r in q.order_by(AuditLog.id.desc()).limit(limit).all()]
