"""
Advisories, the list of official sources, and emergency numbers (redesign part 4).

Every change is written to the audit log with the person's name (audit.py) and committed
together with the change itself.
"""
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException, Request
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from . import audit, config
from .accounts import normalize_name
from .database import engine as default_engine
from .models import Advisory, AdvisorySource, EmergencyNumber, User


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like the other tables


# ---------------------------------------------------------------- tables made on start

def prepare_tables(engine=default_engine) -> None:
    """
    Make the two list tables and fill them with their starting rows, ONCE: only when the table
    did not exist yet. So a Super admin who removes a source or the 911 row does not get it
    back on the next start. Call this BEFORE Base.metadata.create_all. No existing table gets a
    new column in part 4, so there is no column upgrade here.
    """
    insp = inspect(engine)
    had_sources = insp.has_table(AdvisorySource.__tablename__)
    had_numbers = insp.has_table(EmergencyNumber.__tablename__)
    AdvisorySource.__table__.create(engine, checkfirst=True)
    EmergencyNumber.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        if not had_sources:
            for name in config.DEFAULT_OFFICIAL_SOURCES:
                db.add(AdvisorySource(name=name, name_key=normalize_name(name)))
        if not had_numbers:
            for position, (number, name) in enumerate(config.DEFAULT_EMERGENCY_NUMBERS):
                db.add(EmergencyNumber(number=number, name=name, position=position))
        db.commit()


def _get_or_404(db: Session, model, row_id: int, what: str):
    row = db.get(model, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"That {what} was not found.")
    return row


# ---------------------------------------------------------------- official sources

def official_keys(db: Session) -> set:
    return {key for (key,) in db.query(AdvisorySource.name_key).all()}


def list_sources(db: Session) -> List[AdvisorySource]:
    return db.query(AdvisorySource).order_by(AdvisorySource.id).all()


def add_source(db: Session, user: User, name: str, request: Request) -> AdvisorySource:
    key = normalize_name(name)
    if db.query(AdvisorySource).filter(AdvisorySource.name_key == key).first():
        raise HTTPException(status_code=409, detail="That source is already on the official list.")
    row = AdvisorySource(name=name, name_key=key)
    db.add(row)
    db.flush()
    audit.record(db, user, "advisory_source.add", target=f"source:{row.id} ({name})", request=request)
    db.commit()
    return row


def rename_source(db: Session, user: User, source_id: int, name: str, request: Request) -> AdvisorySource:
    row = _get_or_404(db, AdvisorySource, source_id, "source")
    key = normalize_name(name)
    clash = db.query(AdvisorySource).filter(AdvisorySource.name_key == key, AdvisorySource.id != row.id).first()
    if clash:
        raise HTTPException(status_code=409, detail="That source is already on the official list.")
    old = row.name
    row.name, row.name_key = name, key
    audit.record(db, user, "advisory_source.update", target=f"source:{row.id} ({name})", detail={"was": old}, request=request)
    db.commit()
    return row


def remove_source(db: Session, user: User, source_id: int, request: Request) -> None:
    row = _get_or_404(db, AdvisorySource, source_id, "source")
    audit.record(db, user, "advisory_source.remove", target=f"source:{row.id} ({row.name})", request=request)
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------- advisories

def list_advisories(db: Session, official_only: bool = False, limit: int = 50):
    """(advisory, is_official) pairs: pinned first, then newest first."""
    keys = official_keys(db)
    rows = db.query(Advisory).order_by(Advisory.pinned.desc(), Advisory.created_at.desc(), Advisory.id.desc()).all()
    pairs = [(a, normalize_name(a.source) in keys) for a in rows]
    if official_only:
        pairs = [p for p in pairs if p[1]]
    return pairs[:limit]


def _out_pair(db: Session, a: Advisory):
    return a, normalize_name(a.source) in official_keys(db)


def create_advisory(db: Session, user: User, payload, request: Request):
    a = Advisory(
        title=payload.title, details=payload.details, source=payload.organization,
        source_url=payload.source_url, pinned=payload.pinned, created_by=user.name,
    )
    db.add(a)
    db.flush()
    audit.record(
        db, user, "advisory.create", target=f"advisory:{a.id} ({a.title})",
        detail={"organization": a.source, "pinned": a.pinned}, request=request,
    )
    db.commit()
    return _out_pair(db, a)


def update_advisory(db: Session, user: User, advisory_id: int, payload, request: Request):
    a = _get_or_404(db, Advisory, advisory_id, "advisory")
    changed = []
    for field, column in (("title", "title"), ("details", "details"), ("organization", "source"), ("source_url", "source_url")):
        value = getattr(payload, field)
        if field in payload.model_fields_set and value is not None and getattr(a, column) != value:
            setattr(a, column, value)
            changed.append(field)
    if changed:
        a.updated_at, a.updated_by = utcnow_naive(), user.name
        audit.record(db, user, "advisory.update", target=f"advisory:{a.id} ({a.title})", detail={"changed": changed}, request=request)
        db.commit()
    return _out_pair(db, a)


def set_pinned(db: Session, user: User, advisory_id: int, pinned: bool, request: Request):
    a = _get_or_404(db, Advisory, advisory_id, "advisory")
    if bool(a.pinned) != pinned:  # safe to call twice: the second call changes and logs nothing
        a.pinned = pinned
        audit.record(db, user, "advisory.pin" if pinned else "advisory.unpin", target=f"advisory:{a.id} ({a.title})", request=request)
        db.commit()
    return _out_pair(db, a)


def delete_advisory(db: Session, user: User, advisory_id: int, request: Request) -> None:
    a = _get_or_404(db, Advisory, advisory_id, "advisory")
    audit.record(db, user, "advisory.delete", target=f"advisory:{a.id} ({a.title})", detail={"organization": a.source}, request=request)
    db.delete(a)
    db.commit()


# ---------------------------------------------------------------- emergency numbers

def list_numbers(db: Session) -> List[EmergencyNumber]:
    return db.query(EmergencyNumber).order_by(EmergencyNumber.position, EmergencyNumber.id).all()


def add_number(db: Session, user: User, payload, request: Request) -> EmergencyNumber:
    last = db.query(EmergencyNumber.position).order_by(EmergencyNumber.position.desc()).first()
    n = EmergencyNumber(
        number=payload.number, name=payload.name, description=payload.description,
        position=(last[0] + 1) if last else 0,
    )
    db.add(n)
    db.flush()
    audit.record(db, user, "emergency_number.add", target=f"number:{n.id} ({n.name})", detail={"number": n.number}, request=request)
    db.commit()
    return n


def update_number(db: Session, user: User, number_id: int, payload, request: Request) -> EmergencyNumber:
    n = _get_or_404(db, EmergencyNumber, number_id, "emergency number")
    changed, before = [], {}
    for field in ("number", "name", "description"):
        if field in payload.model_fields_set and getattr(n, field) != getattr(payload, field):
            before[field] = getattr(n, field)
            setattr(n, field, getattr(payload, field))
            changed.append(field)
    if changed:
        audit.record(
            db, user, "emergency_number.update", target=f"number:{n.id} ({n.name})",
            detail={"changed": changed, "was": before}, request=request,
        )
        db.commit()
    return n


def remove_number(db: Session, user: User, number_id: int, request: Request) -> None:
    n = _get_or_404(db, EmergencyNumber, number_id, "emergency number")
    audit.record(db, user, "emergency_number.remove", target=f"number:{n.id} ({n.name})", detail={"number": n.number}, request=request)
    db.delete(n)
    db.commit()


def reorder_numbers(db: Session, user: User, ids: List[int], request: Request) -> List[EmergencyNumber]:
    rows = {n.id: n for n in db.query(EmergencyNumber).all()}
    if sorted(ids) != sorted(rows):
        raise HTTPException(status_code=422, detail="The order must list every emergency number exactly once.")
    for position, number_id in enumerate(ids):
        rows[number_id].position = position
    audit.record(db, user, "emergency_number.reorder", target="emergency_numbers", detail={"order": ids}, request=request)
    db.commit()
    return list_numbers(db)
