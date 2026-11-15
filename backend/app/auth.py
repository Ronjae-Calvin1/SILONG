"""
The server-side role check. Use these as FastAPI dependencies on admin routes:

    from .auth import require_responder, require_super_admin

    @router.get("/api/something")                       # any staff (responder or Super admin)
    def something(user: User = Depends(require_responder)): ...

    @router.get("/api/admin/something")                 # Super admin only
    def something(user: User = Depends(require_super_admin)): ...

No token -> 401. Expired (idle) or unknown token -> 401. Right sign-in but the
role is too low -> 403. The check happens on the server, whatever the screens show.
A Super admin passes every check a responder passes.
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
    """Any signed-in staff member. Also moves their idle timer forward."""
    return accounts.user_for_token(db, token)


def require_role(minimum: str):
    """A dependency that lets through the given role and every role above it."""
    needed = accounts.ROLE_RANK[minimum]

    def check(user: User = Depends(current_user)) -> User:
        if accounts.ROLE_RANK.get(user.role, 0) < needed:
            raise HTTPException(status_code=403, detail="You do not have permission to do this.")
        return user

    return check


require_responder = require_role(accounts.RESPONDER)
require_super_admin = require_role(accounts.SUPER_ADMIN)
