"""
The server-side sign-in check. There is ONE role, Admin, so there is one dependency to use on every
admin route:

    from .auth import require_admin

    @router.get("/api/admin/something")
    def something(user: User = Depends(require_admin)): ...

For a PUBLIC route where a signed-in Admin counts as an official (a status update), use
`optional_staff`: it gives the Admin or None and never raises.

No token -> 401. Expired (idle) or unknown token -> 401. A live sign-in whose account is locked or
gone -> 403. Nothing is locked by role: every Admin passes every check. The check happens on the
server, whatever the screens show.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import accounts
from .database import get_db
from .models import User


def bearer_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """The token from `Authorization: Bearer <token>`, or None."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def current_user(token: Optional[str] = Depends(bearer_token), db: Session = Depends(get_db)) -> User:
    """Any signed-in account. Also moves their idle timer forward."""
    return accounts.user_for_token(db, token)


def require_admin(user: User = Depends(current_user)) -> User:
    """The one check for admin routes: a signed-in Admin (401 without a good sign-in, 403 for a locked or removed account)."""
    if user.role != accounts.ADMIN:
        raise HTTPException(status_code=403, detail="You do not have permission to do this.")
    return user


def optional_staff(token: Optional[str] = Depends(bearer_token), db: Session = Depends(get_db)) -> Optional[User]:
    """
    For PUBLIC routes where a signed-in Admin counts as an official (a status update). No token, or a
    token that is wrong, too old or belongs to a locked account, means "not signed in": None, never a
    401 or 403, so the person is simply treated as a user. A good token moves the idle timer forward,
    like current_user does.
    """
    if not token:
        return None
    try:
        user = accounts.user_for_token(db, token)
    except HTTPException:
        return None
    return user if user.role == accounts.ADMIN else None
