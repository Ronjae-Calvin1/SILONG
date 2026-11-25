"""
Audit log helper. Every admin action is written here with the person's name.

Later parts call it from their admin routes, like this:

    from . import audit
    audit.record(db, user, "report.resolve", target="report:12", detail={"note": "Sent a team"}, request=request)
    db.commit()

- `user` is the signed-in Admin from the check (auth.require_admin).
- `action` is "<thing>.<verb>", for example "user.create" or "place.approve".
- It only adds the row to the session and does NOT commit. Commit once, together
  with the change itself, so an action and its log entry are saved together or not
  at all.
- Never put a password, token or phone number in `detail`.
- The IP is stored hashed only.
"""
import json
from typing import Any, Optional, Union

from fastapi import Request
from sqlalchemy.orm import Session

from .evac_service import hash_ip
from .models import AuditLog, User


def record(
    db: Session,
    actor: Union[User, str, None],
    action: str,
    target: Optional[str] = None,
    detail: Any = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """Add an audit entry. `actor` may also be a plain name (for scripts) or None (shown as "(system)")."""
    if isinstance(actor, User):
        actor_id, name, role = actor.id, actor.name, actor.role
    else:
        actor_id, name, role = None, actor or "(system)", None

    ip_hash = None
    if request is not None:
        ip_hash = hash_ip(request.client.host if request.client else "unknown")

    entry = AuditLog(
        actor_id=actor_id,
        actor_name=name,
        actor_role=role,
        action=action,
        target=target,
        detail=None if detail is None else json.dumps(detail, ensure_ascii=False, default=str),
        ip_hash=ip_hash,
    )
    db.add(entry)
    return entry
