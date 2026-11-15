"""
Staff accounts: create, sign in, sessions, lock / unlock / remove.

Roles (docs/REDESIGN.md): "responder" and "super_admin". The public has no
account. A Super admin can do everything a responder can, so role checks use a
rank (see ROLE_RANK) and "responder" means "responder or above".

Errors are raised as AccountError (an HTTPException with a plain-language
message), so routes and the setup script can both use these functions.
Functions here commit their own changes unless the docstring says otherwise.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import audit, config
from .models import AuthSession, User
from .security import DUMMY_HASH, hash_password, hash_token, new_token, verify_password

RESPONDER = "responder"
SUPER_ADMIN = "super_admin"
ROLES = (RESPONDER, SUPER_ADMIN)
ROLE_RANK = {RESPONDER: 1, SUPER_ADMIN: 2}

NAME_MIN, NAME_MAX = 2, 50
PASSWORD_MAX = 200  # keeps one sign-in from being a heavy request


class AccountError(HTTPException):
    def __init__(self, status_code: int, message: str, headers: Optional[dict] = None):
        super().__init__(status_code=status_code, detail=message, headers=headers)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like the other tables


def normalize_name(name: str) -> str:
    """Sign-in key: case and extra spaces do not matter ("ana  CRUZ" = "Ana Cruz")."""
    return re.sub(r"\s+", " ", name).strip().casefold()


def _minutes_left(until: datetime, now: datetime) -> int:
    return max(1, int((until - now).total_seconds() / 60 + 0.999))


# ---------------------------------------------------------------- create

def create_user(
    db: Session, name: str, password: str, role: str,
    actor: Union[User, str], request: Optional[Request] = None, extra_detail: Optional[dict] = None,
) -> User:
    """Adds the account (hashed password) and its audit entry in one commit. `actor` is the creator (a User, or a name for scripts)."""
    clean = re.sub(r"\s+", " ", name).strip()
    if not (NAME_MIN <= len(clean) <= NAME_MAX):
        raise AccountError(422, f"The name must be {NAME_MIN} to {NAME_MAX} characters.")
    if role not in ROLES:
        raise AccountError(422, "The role must be responder or super_admin.")
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise AccountError(422, f"The password must be at least {config.MIN_PASSWORD_LENGTH} characters.")
    if len(password) > PASSWORD_MAX:
        raise AccountError(422, f"The password must be at most {PASSWORD_MAX} characters.")
    key = normalize_name(clean)
    if db.query(User).filter(User.name_key == key).first():
        raise AccountError(409, "An account with that name already exists.")

    created_by = actor.name if isinstance(actor, User) else actor
    user = User(name=clean, name_key=key, password_hash=hash_password(password), role=role, created_by=created_by)
    db.add(user)
    db.flush()  # gives the new account its id for the log entry
    audit.record(db, actor, "user.create", target=f"user:{user.id} ({user.name})", detail={"role": role, **(extra_detail or {})}, request=request)
    db.commit()
    db.refresh(user)
    return user


def has_super_admin(db: Session) -> bool:
    return db.query(User).filter(User.role == SUPER_ADMIN).first() is not None


def create_first_super_admin(db: Session, name: str, password: str) -> User:
    """Used by scripts/create_super_admin.py. Refuses when a Super admin already exists."""
    if has_super_admin(db):
        raise AccountError(409, "A Super admin already exists. Sign in and create more accounts from the app.")
    return create_user(db, name, password, SUPER_ADMIN, actor="setup script", extra_detail={"first_super_admin": True})


# ---------------------------------------------------------------- sign in / out

def sign_in(db: Session, name: str, password: str, request: Optional[Request] = None) -> Tuple[str, User]:
    """
    Checks the password, enforces the lock, and starts a session.
    Returns (token, user). The token is shown to the browser once; only its hash is stored.
    """
    wrong = AccountError(401, "The name or password is wrong.")
    user = db.query(User).filter(User.name_key == normalize_name(name)).first()
    if user is None:
        verify_password(password, DUMMY_HASH)  # spend the same time as a real check
        raise wrong

    now = _now()
    if user.is_locked:
        raise AccountError(423, "This account is locked. Ask a Super admin to unlock it.")
    if user.locked_until is not None:
        if user.locked_until > now:
            raise AccountError(423, f"Too many wrong tries. This account is locked. Try again in about {_minutes_left(user.locked_until, now)} minute(s).")
        user.locked_until = None  # the lock ran out: start fresh
        user.failed_attempts = 0

    if not verify_password(password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= config.SIGNIN_MAX_WRONG_TRIES:
            user.failed_attempts = 0
            user.locked_until = now + timedelta(minutes=config.SIGNIN_LOCK_MINUTES)
            audit.record(db, user, "auth.auto_lock", target=f"user:{user.id} ({user.name})",
                         detail={"wrong_tries": config.SIGNIN_MAX_WRONG_TRIES, "minutes": config.SIGNIN_LOCK_MINUTES}, request=request)
            db.commit()
            raise AccountError(423, f"Too many wrong tries. This account is locked for {config.SIGNIN_LOCK_MINUTES} minutes.")
        db.commit()
        raise wrong

    user.failed_attempts = 0
    user.locked_until = None
    user.last_sign_in_at = now
    _drop_idle_sessions(db, now)  # housekeeping: forget sessions that already ran out
    token = new_token()
    db.add(AuthSession(token_hash=hash_token(token), user_id=user.id, created_at=now, last_used_at=now))
    audit.record(db, user, "auth.sign_in", target=f"user:{user.id} ({user.name})", request=request)
    db.commit()
    return token, user


def _idle_limit() -> timedelta:
    return timedelta(minutes=config.STAFF_IDLE_MINUTES)


def _drop_idle_sessions(db: Session, now: datetime) -> None:
    db.query(AuthSession).filter(AuthSession.last_used_at < now - _idle_limit()).delete(synchronize_session=False)


def user_for_token(db: Session, token: Optional[str]) -> User:
    """
    The signed-in user for a token, or a 401. Each good request moves the idle
    timer forward; a session unused for STAFF_IDLE_MINUTES is deleted.
    """
    if not token:
        raise AccountError(401, "Please sign in.", {"WWW-Authenticate": "Bearer"})
    now = _now()
    session = db.query(AuthSession).filter(AuthSession.token_hash == hash_token(token)).first()
    if session is None:
        raise AccountError(401, "Your sign-in is no longer valid. Please sign in again.", {"WWW-Authenticate": "Bearer"})
    if now - session.last_used_at > _idle_limit():
        db.delete(session)
        db.commit()
        raise AccountError(401, f"You were signed out after {config.STAFF_IDLE_MINUTES} minutes without use. Please sign in again.", {"WWW-Authenticate": "Bearer"})
    user = db.get(User, session.user_id)
    if user is None or user.is_locked:
        db.delete(session)
        db.commit()
        raise AccountError(401, "Your sign-in is no longer valid. Please sign in again.", {"WWW-Authenticate": "Bearer"})
    session.last_used_at = now
    db.commit()
    return user


def sign_out(db: Session, token: Optional[str], request: Optional[Request] = None) -> None:
    """Ends the session. A token that is already gone is fine: the result is the same."""
    if not token:
        return
    session = db.query(AuthSession).filter(AuthSession.token_hash == hash_token(token)).first()
    if session is None:
        return
    user = db.get(User, session.user_id)
    db.delete(session)
    if user is not None:
        audit.record(db, user, "auth.sign_out", target=f"user:{user.id} ({user.name})", request=request)
    db.commit()


def end_sessions(db: Session, user_id: int) -> None:
    db.query(AuthSession).filter(AuthSession.user_id == user_id).delete(synchronize_session=False)


# ---------------------------------------------------------------- Super admin actions

def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AccountError(404, "Account not found.")
    return user


def lock_user(db: Session, actor: User, target: User, request: Optional[Request] = None) -> bool:
    """Locks until a Super admin unlocks it and signs the person out. False if it was already locked."""
    if target.id == actor.id:
        raise AccountError(409, "You cannot lock your own account.")
    if target.is_locked:
        return False
    target.is_locked = True
    end_sessions(db, target.id)
    audit.record(db, actor, "user.lock", target=f"user:{target.id} ({target.name})", request=request)
    db.commit()
    return True


def unlock_user(db: Session, actor: User, target: User, request: Optional[Request] = None) -> None:
    """Clears both kinds of lock (by a Super admin, and the automatic one) and the wrong-try count."""
    target.is_locked = False
    target.locked_until = None
    target.failed_attempts = 0
    audit.record(db, actor, "user.unlock", target=f"user:{target.id} ({target.name})", request=request)
    db.commit()


def remove_user(db: Session, actor: User, target: User, request: Optional[Request] = None) -> None:
    """Deletes the account and its sessions. Its audit entries stay, with the name as text."""
    if target.id == actor.id:
        raise AccountError(409, "You cannot remove your own account.")
    end_sessions(db, target.id)
    audit.record(db, actor, "user.remove", target=f"user:{target.id} ({target.name})", detail={"role": target.role}, request=request)
    db.delete(target)
    db.commit()
