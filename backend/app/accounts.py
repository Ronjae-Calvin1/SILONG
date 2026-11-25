"""
Admin accounts: create, sign in, sessions, lock / unlock / remove.

There is ONE role, "admin" (ADMIN_CONSOLE.md). Every Admin can do everything; nothing is locked by
role. The public has no account. Databases made before the single-role change hold accounts with
the old roles "responder" and "super_admin": migrate_roles() turns them into "admin" on startup.

Errors are raised as AccountError (an HTTPException with a plain-language
message), so routes and the setup script can both use these functions.
Functions here commit their own changes unless the docstring says otherwise.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import audit, config
from .database import SessionLocal
from .models import AuthSession, User
from .rate_limit import password_change_limiter
from .security import DUMMY_HASH, hash_password, hash_token, new_token, verify_password

log = logging.getLogger("silong.accounts")

ADMIN = "admin"
# Roles of the older two-role design. Only the startup migration and the (ignored) legacy `role`
# field of account creation know them; nothing is checked against them any more.
LEGACY_ROLES = ("responder", "super_admin")

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


def check_password_length(password: str) -> None:
    """The one place the password length rules live (account creation, change and reset)."""
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise AccountError(422, f"The password must be at least {config.MIN_PASSWORD_LENGTH} characters.")
    if len(password) > PASSWORD_MAX:
        raise AccountError(422, f"The password must be at most {PASSWORD_MAX} characters.")


# ---------------------------------------------------------------- create

def create_user(
    db: Session, name: str, password: str,
    actor: Union[User, str], request: Optional[Request] = None, extra_detail: Optional[dict] = None,
) -> User:
    """Adds an Admin account (hashed password) and its audit entry in one commit. `actor` is the creator (a User, or a name for scripts)."""
    clean = re.sub(r"\s+", " ", name).strip()
    if not (NAME_MIN <= len(clean) <= NAME_MAX):
        raise AccountError(422, f"The name must be {NAME_MIN} to {NAME_MAX} characters.")
    check_password_length(password)
    key = normalize_name(clean)
    if db.query(User).filter(User.name_key == key).first():
        raise AccountError(409, "An account with that name already exists.")

    created_by = actor.name if isinstance(actor, User) else actor
    user = User(name=clean, name_key=key, password_hash=hash_password(password), role=ADMIN, created_by=created_by)
    db.add(user)
    db.flush()  # gives the new account its id for the log entry
    audit.record(db, actor, "user.create", target=f"user:{user.id} ({user.name})", detail={"role": ADMIN, **(extra_detail or {})}, request=request)
    db.commit()
    db.refresh(user)
    return user


def has_admin(db: Session) -> bool:
    return db.query(User).filter(User.role == ADMIN).first() is not None


def create_first_admin(db: Session, name: str, password: str) -> User:
    """Used by scripts/create_admin.py. Refuses when an Admin already exists."""
    if has_admin(db):
        raise AccountError(409, "An Admin already exists. Sign in and create more accounts from the app.")
    return create_user(db, name, password, actor="setup script", extra_detail={"first_admin": True})


def active_admin_count(db: Session, excluding: Optional[User] = None) -> int:
    """How many Admins are not locked by an Admin (a temporary wrong-tries lock still counts: it runs out by itself)."""
    q = db.query(User).filter(User.role == ADMIN, User.is_locked.is_(False))
    if excluding is not None:
        q = q.filter(User.id != excluding.id)
    return q.count()


# ---------------------------------------------------------------- one-role migration

def migrate_roles(db: Session) -> int:
    """
    Turns every account with an old role ("responder" or "super_admin") into an Admin. Safe to run
    again: once nothing has an old role it does nothing (and writes nothing). Each change is logged
    to the audit log as "(system)" with the old role, and the total goes to the server log.
    Returns how many accounts it changed. Commits.
    """
    rows = db.query(User).filter(User.role.in_(LEGACY_ROLES)).order_by(User.id).all()
    for user in rows:
        audit.record(db, None, "user.role_migrated", target=f"user:{user.id} ({user.name})",
                     detail={"from": user.role, "to": ADMIN})
        user.role = ADMIN
    if rows:
        db.commit()
        log.info("Role migration: %s account(s) are Admins now (they had the old responder or super_admin role).", len(rows))
    return len(rows)


def migrate_roles_on_startup() -> int:
    """Runs migrate_roles with its own session. Called by main.py after the tables exist."""
    db = SessionLocal()
    try:
        return migrate_roles(db)
    finally:
        db.close()


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
        raise AccountError(423, "This account is locked. Ask another Admin to unlock it.")
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
    The signed-in user for a token. Each good request moves the idle timer forward; a session
    unused for STAFF_IDLE_MINUTES is deleted.

    No token, an unknown token or an idle session -> 401. A session that is still alive but whose
    account is locked or no longer exists -> 403 (and the session is deleted, so the next try is a
    401). Locking or removing an account through the API already ends its sessions, so the 403 is
    the backstop for a lock or removal made another way.
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
        locked = user is not None
        db.delete(session)
        db.commit()
        raise AccountError(403, "This account is locked. Ask another Admin to unlock it." if locked else "This account no longer exists.")
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


# ---------------------------------------------------------------- account actions (any Admin)

def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AccountError(404, "Account not found.")
    return user


def lock_user(db: Session, actor: User, target: User, request: Optional[Request] = None) -> bool:
    """Locks until an Admin unlocks it and signs the person out. False if it was already locked."""
    if target.id == actor.id:
        raise AccountError(409, "You cannot lock your own account.")
    if target.is_locked:
        return False
    if active_admin_count(db, excluding=target) == 0:
        raise AccountError(409, "You cannot lock the last active Admin.")
    target.is_locked = True
    end_sessions(db, target.id)
    audit.record(db, actor, "user.lock", target=f"user:{target.id} ({target.name})", request=request)
    db.commit()
    return True


def unlock_user(db: Session, actor: User, target: User, request: Optional[Request] = None) -> None:
    """Clears both kinds of lock (by an Admin, and the automatic one) and the wrong-try count."""
    target.is_locked = False
    target.locked_until = None
    target.failed_attempts = 0
    audit.record(db, actor, "user.unlock", target=f"user:{target.id} ({target.name})", request=request)
    db.commit()


def remove_user(db: Session, actor: User, target: User, request: Optional[Request] = None) -> None:
    """Deletes the account and its sessions. Its audit entries stay, with the name as text."""
    if target.id == actor.id:
        raise AccountError(409, "You cannot remove your own account.")
    if not target.is_locked and active_admin_count(db, excluding=target) == 0:
        raise AccountError(409, "You cannot remove the last active Admin.")
    end_sessions(db, target.id)
    audit.record(db, actor, "user.remove", target=f"user:{target.id} ({target.name})", detail={"role": target.role}, request=request)
    db.delete(target)
    db.commit()


# ---------------------------------------------------------------- passwords

def change_password(
    db: Session, user: User, token: Optional[str], current_password: str, new_password: str,
    ip: str, request: Optional[Request] = None,
) -> int:
    """
    Changes the signed-in person's own password. A wrong current password is refused (403) and counts
    toward a limit per person and per IP (429 once it is used up), so it cannot be used to guess.
    On success every OTHER session of this person ends and the one making the request stays.
    Returns how many other sessions it ended. Nothing about either password is logged.
    """
    check_password_length(new_password)  # first: a refused new password says nothing about the current one
    keys = (f"user:{user.id}", f"ip:{ip}")
    wait = password_change_limiter.blocked(keys)
    if wait is not None:
        minutes = max(1, round(wait / 60))
        raise AccountError(429, f"Too many wrong passwords. Please try again in about {minutes} minute(s).", {"Retry-After": str(wait)})
    if not verify_password(current_password, user.password_hash):
        password_change_limiter.fail(keys)
        raise AccountError(403, "The current password is wrong.")
    if verify_password(new_password, user.password_hash):
        raise AccountError(422, "The new password must be different from the current one.")

    password_change_limiter.clear(keys[0])
    user.password_hash = hash_password(new_password)
    q = db.query(AuthSession).filter(AuthSession.user_id == user.id)
    if token:
        q = q.filter(AuthSession.token_hash != hash_token(token))
    ended = q.delete(synchronize_session=False)
    audit.record(db, user, "auth.change_password", target=f"user:{user.id} ({user.name})",
                 detail={"other_sessions_ended": ended}, request=request)
    db.commit()
    return ended


def reset_password(db: Session, actor: User, target: User, new_password: str, request: Optional[Request] = None) -> int:
    """
    An Admin sets a new password for someone else. Ends ALL of that person's sessions and clears
    their wrong-try count and the automatic lock. A lock an Admin set (is_locked) stays: it is a
    separate decision, undone with unlock. Returns how many sessions it ended.
    """
    if target.id == actor.id:
        raise AccountError(409, "To change your own password, use Change password with your current password.")
    check_password_length(new_password)
    target.password_hash = hash_password(new_password)
    target.failed_attempts = 0
    target.locked_until = None
    ended = db.query(AuthSession).filter(AuthSession.user_id == target.id).delete(synchronize_session=False)
    password_change_limiter.clear(f"user:{target.id}")
    audit.record(db, actor, "user.reset_password", target=f"user:{target.id} ({target.name})",
                 detail={"sessions_ended": ended}, request=request)
    db.commit()
    return ended


def purge_idle_sessions(db: Session, now: Optional[datetime] = None) -> int:
    """Delete sessions unused for longer than STAFF_IDLE_MINUTES (they are dead already). Returns how many."""
    deleted = db.query(AuthSession).filter(AuthSession.last_used_at < (now or _now()) - _idle_limit()).delete(synchronize_session=False)
    db.commit()
    return deleted
