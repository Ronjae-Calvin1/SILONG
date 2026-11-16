"""
Help requests and hazard reports: rules and queries. The routes are in
report_routes.py and only call the functions here.

Two kinds of report (docs/REDESIGN.md, "Help requests and hazard reports"):

  help    "I need help". Goes to responders only. Never public. The sender sees
          only their own reports and a status: New, Being handled, Resolved.
  hazard  People within the near-me range see an approximate spot with no
          details. It is "Unconfirmed" after HAZARD_UNCONFIRMED_PHONES reports
          from different phones, and "Verified" once a responder or Super admin
          verifies it. Until one of those, only responders (and the sender, in
          "my reports") see it.

Phone ID: a random value from the browser, used for "my reports". It is not
proof of identity. Only its SHA-256 hash is stored (no salt on purpose: it must
stay the same after a restart, and the ID is long and random, so a salt adds
nothing). A hash is never sent out.

Hazards about the same place: a new hazard report within HAZARD_MERGE_METERS of
the first report of an OPEN hazard joins it (same group_id). One phone counts
once per hazard: a second report from the same phone for the same hazard
returns the first one. Responder actions on a hazard apply to the whole group.
A closed (resolved or false) hazard is never joined; a new report starts a new one.

Functions here add rows and audit entries to the session; the ones that
change data commit once at the end (the change and its audit entry together).
"""
import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import audit, config
from .database import SessionLocal
from .evac_service import distance_m, hash_ip
from .models import BlockedPhone, ForgivenPhone, Report, User

HELP, HAZARD = "help", "hazard"
NEW, BEING_HANDLED, RESOLVED, FALSE = "new", "being_handled", "resolved", "false"
OPEN = (NEW, BEING_HANDLED)

# What the SENDER sees. A report marked false shows as Resolved: the sender
# gets the three words from the design, and never the reason.
PUBLIC_STATUS = {NEW: "new", BEING_HANDLED: "being_handled", RESOLVED: "resolved", FALSE: "resolved"}
PUBLIC_LABEL = {"new": "New", "being_handled": "Being handled", "resolved": "Resolved"}

PHONE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
METERS_PER_DEGREE = 111_320


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like the other tables


class ReportError(HTTPException):
    def __init__(self, status_code: int, message: str, headers: Optional[dict] = None):
        super().__init__(status_code=status_code, detail=message, headers=headers)


# ------------------------------------------------------------ phone ID

def hash_phone_id(phone_id: str) -> str:
    return hashlib.sha256(f"silong-phone-v1:{phone_id}".encode()).hexdigest()


def phone_hash_from_header(value: Optional[str], required: bool) -> Optional[str]:
    """The stored hash for the X-Phone-Id header. Missing or malformed -> 400 (when required)."""
    if value is None or value == "":
        if required:
            raise ReportError(400, "A phone ID is required (header X-Phone-Id: 16 to 64 letters, digits, - or _).")
        return None
    if not PHONE_ID_RE.match(value):
        raise ReportError(400, "The phone ID is not valid (header X-Phone-Id: 16 to 64 letters, digits, - or _).")
    return hash_phone_id(value)


def block_expires_at(row: BlockedPhone) -> Optional[datetime]:
    """When a block ends by itself (config.BLOCK_EXPIRES_DAYS), or None when it never does."""
    if config.BLOCK_EXPIRES_DAYS <= 0:
        return None
    return row.blocked_at + timedelta(days=config.BLOCK_EXPIRES_DAYS)


def _block_expired(row: BlockedPhone, now: Optional[datetime] = None) -> bool:
    end = block_expires_at(row)
    return end is not None and end <= (now or _now())


def is_blocked(db: Session, phone_hash: str) -> bool:
    """True while the phone is blocked. A block that has run out no longer counts, even before the cleanup removes its row."""
    row = db.query(BlockedPhone).filter(BlockedPhone.phone_hash == phone_hash).first()
    return row is not None and not _block_expired(row)


def _forgive(db: Session, phone_hash: str, now: Optional[datetime] = None) -> None:
    """Start the phone's false-report count from zero (see ForgivenPhone). The caller commits."""
    now = now or _now()
    row = db.get(ForgivenPhone, phone_hash)
    if row is None:
        db.add(ForgivenPhone(phone_hash=phone_hash, since=now))
    else:
        row.since = now


def lift_expired_blocks(db: Session, now: Optional[datetime] = None) -> int:
    """
    Remove the blocks that have run out (config.BLOCK_EXPIRES_DAYS; 0 = never). Each lifted phone
    starts with a clean false-report count. Returns how many it lifted and writes one audit entry
    (as "(system)") when it lifted any. Safe to run any time.
    """
    if config.BLOCK_EXPIRES_DAYS <= 0:
        return 0
    now = now or _now()
    lifted = 0
    for row in db.query(BlockedPhone).all():
        if _block_expired(row, now):
            _forgive(db, row.phone_hash, now)
            db.delete(row)
            lifted += 1
    if lifted:
        audit.record(db, None, "report.block_expired", detail={"lifted": lifted, "after_days": config.BLOCK_EXPIRES_DAYS})
    db.commit()
    return lifted


def list_blocked_phones(db: Session) -> List[dict]:
    """Blocked phones, newest first. Only the row number, the date and the count: never the phone ID or its hash."""
    out = []
    for row in db.query(BlockedPhone).order_by(BlockedPhone.id.desc()).all():
        if _block_expired(row):
            continue
        out.append(dict(id=row.id, blocked_at=row.blocked_at, false_reports=row.false_reports, expires_at=block_expires_at(row)))
    return out


def unblock_phone(db: Session, user: User, block_id: int, request: Optional[Request]) -> dict:
    """Lets the phone send reports again, with a fresh false-report count. Audited with the person's name."""
    row = db.get(BlockedPhone, block_id)
    if row is None:
        raise ReportError(404, "That blocked phone was not found. It may already have been unblocked.")
    info = dict(id=row.id, false_reports=row.false_reports)
    _forgive(db, row.phone_hash)
    db.delete(row)
    audit.record(db, user, "report.phone_unblocked", target=f"blocked_phone:{info['id']}",
                 detail={"false_reports": info["false_reports"]}, request=request)
    db.commit()
    return info


# ------------------------------------------------------------ locations

def approximate(lat: float, lng: float) -> Tuple[float, float]:
    """
    The middle of the HAZARD_APPROX_METERS square the point falls in. The same
    point always gives the same answer, so asking again and again cannot
    average the error away.
    """
    step_lat = config.HAZARD_APPROX_METERS / METERS_PER_DEGREE
    step_lng = step_lat / max(math.cos(math.radians(lat)), 0.01)
    return (
        round((math.floor(lat / step_lat) + 0.5) * step_lat, 5),
        round((math.floor(lng / step_lng) + 0.5) * step_lng, 5),
    )


# ------------------------------------------------------------ hazard groups

def hazard_state(rows: List[Report]) -> str:
    """\"verified\" | \"unconfirmed\" | \"pending\" (not enough different phones yet, not public)."""
    if any(r.verified_at is not None for r in rows):
        return "verified"
    if len({r.phone_hash for r in rows}) >= config.HAZARD_UNCONFIRMED_PHONES:
        return "unconfirmed"
    return "pending"


def _group_rows(rows: List[Report]) -> Dict[int, List[Report]]:
    groups: Dict[int, List[Report]] = defaultdict(list)
    for r in rows:
        groups[r.group_id if r.group_id is not None else r.id].append(r)
    for g in groups.values():
        g.sort(key=lambda r: r.id)
    return groups


def _open_hazard_groups(db: Session) -> Dict[int, List[Report]]:
    rows = db.query(Report).filter(Report.kind == HAZARD, Report.status.in_(OPEN)).order_by(Report.id).all()
    return _group_rows(rows)


def _hazard_group_of(db: Session, row: Report) -> List[Report]:
    return db.query(Report).filter(Report.kind == HAZARD, Report.group_id == row.group_id).order_by(Report.id).all()


# ------------------------------------------------------------ sending

def create_report(
    db: Session, kind: str, lat: float, lng: float, contact: Optional[str], note: Optional[str],
    phone_hash: str, ip: str, category: Optional[str] = None,
    people: Optional[int] = None, can_move: Optional[str] = None,
) -> Tuple[Report, bool]:
    """
    Add a report. Returns (report, created). created is False when this phone
    already reported this hazard: the earlier report is returned and nothing is added.
    The caller checks the block and the limits first and commits afterwards.
    """
    now = _now()
    base = dict(
        kind=kind, phone_hash=phone_hash, ip_hash=hash_ip(ip), latitude=lat, longitude=lng,
        contact=contact, note=note, status=NEW, created_at=now, updated_at=now,
        category=category, people=people, can_move=can_move,
    )
    if kind == HELP:
        row = Report(**base)
        db.add(row)
        return row, True

    # Hazard: join the nearest open hazard within the merge distance, or start one.
    nearest: Optional[List[Report]] = None
    nearest_m = float(config.HAZARD_MERGE_METERS)
    for rows in _open_hazard_groups(db).values():
        d = distance_m(lat, lng, rows[0].latitude, rows[0].longitude)
        if d <= nearest_m:
            nearest, nearest_m = rows, d

    if nearest is None:
        row = Report(**base)
        db.add(row)
        db.flush()  # gets the id
        row.group_id = row.id
        return row, True

    for r in nearest:
        if r.phone_hash == phone_hash:
            return r, False

    first = nearest[0]
    row = Report(**base)
    row.group_id = first.group_id
    row.status = first.status  # a group is always in one state
    row.taken_by, row.taken_at = first.taken_by, first.taken_at
    verified = next((r for r in nearest if r.verified_at is not None), None)
    if verified is not None:
        row.verified_by, row.verified_at = verified.verified_by, verified.verified_at
    db.add(row)
    return row, True


# ------------------------------------------------------------ what the public sees

def reports_of_phone(db: Session, phone_hash: str, limit: int = 100) -> List[dict]:
    """The phone's own reports, newest first: its own location, a status, nothing about who handled it."""
    rows = db.query(Report).filter(Report.phone_hash == phone_hash).order_by(Report.id.desc()).limit(limit).all()
    out = []
    for r in rows:
        status = PUBLIC_STATUS[r.status]
        out.append(dict(
            id=r.id, kind=r.kind, status=status, label=PUBLIC_LABEL[status], category=r.category,
            latitude=r.latitude, longitude=r.longitude, note=r.note,
            created_at=r.created_at, updated_at=r.updated_at,
        ))
    return out


def nearby_hazards(db: Session, lat: float, lng: float) -> List[dict]:
    """
    Open hazards that are Unconfirmed or Verified, within NEAR_ME_KM, as an
    approximate spot and a status. Nothing else. The distance is measured to the
    approximate spot (not the real one), so asking from many places cannot
    reveal more than the spot shows.
    """
    radius_m = config.NEAR_ME_KM * 1000
    out = []
    for rows in _open_hazard_groups(db).values():
        state = hazard_state(rows)
        if state == "pending":
            continue
        a_lat, a_lng = approximate(rows[0].latitude, rows[0].longitude)
        if distance_m(lat, lng, a_lat, a_lng) > radius_m:
            continue
        out.append(dict(
            id=rows[0].id, latitude=a_lat, longitude=a_lng, category=rows[0].category,
            status=state, label="Verified" if state == "verified" else "Unconfirmed",
        ))
    out.sort(key=lambda h: h["id"])
    return out


# ------------------------------------------------------------ what responders see

def _item(rows: List[Report]) -> dict:
    """One line of the responder list: a help request, or a whole hazard group."""
    first = rows[0]
    is_hazard = first.kind == HAZARD
    state = hazard_state(rows) if is_hazard else None
    latest = max(rows, key=lambda r: r.updated_at)
    verified = next((r for r in rows if r.verified_at is not None), None)
    contacts, notes, categories = [], [], []
    for r in rows:
        if r.category and r.category not in categories:
            categories.append(r.category)
        if r.contact and r.contact not in contacts:
            contacts.append(r.contact)
        if r.note and r.note not in notes:
            notes.append(r.note)
    return dict(
        id=first.id, kind=first.kind, status=first.status,
        is_new_help=first.kind == HELP and first.status == NEW,
        category=first.category, categories=categories,
        people=first.people if first.kind == HELP else None,
        can_move=first.can_move if first.kind == HELP else None,
        latitude=first.latitude, longitude=first.longitude,
        contacts=contacts, notes=notes,
        created_at=first.created_at, updated_at=latest.updated_at,
        taken_by=first.taken_by, closed_by=first.closed_by,
        resolution_note=first.resolution_note, false_reason=first.false_reason,
        verified=verified is not None, verified_by=verified.verified_by if verified else None,
        hazard_state=state,
        phones=len({r.phone_hash for r in rows}), report_count=len(rows),
    )


def responder_list(db: Session, include_closed: bool = False, kind: Optional[str] = None) -> dict:
    """
    For the responder screens (poll about every RESPONDER_REFRESH_SECONDS).
    `new_help_count` / `has_new_help` is the red alert: help requests nobody has
    taken yet. They are counted over ALL open reports, whatever the filters are.
    """
    q = db.query(Report)
    if not include_closed:
        q = q.filter(Report.status.in_(OPEN))
    if kind:
        q = q.filter(Report.kind == kind)
    rows = q.order_by(Report.id).all()

    items = [_item([r]) for r in rows if r.kind == HELP]
    items += [_item(g) for g in _group_rows([r for r in rows if r.kind == HAZARD]).values()]

    def order(i: dict):
        rank = 0 if i["is_new_help"] else 1 if i["status"] in OPEN else 2
        return (rank, i["id"] if rank < 2 else -i["id"])  # open: longest waiting first; closed: newest first

    items.sort(key=order)

    new_help = db.query(Report).filter(Report.kind == HELP, Report.status == NEW).count()
    latest = db.query(Report.id).order_by(Report.id.desc()).first()
    return dict(
        server_time=_now(),
        refresh_seconds=config.RESPONDER_REFRESH_SECONDS,
        new_help_count=new_help,
        has_new_help=new_help > 0,
        latest_report_id=latest[0] if latest else None,
        items=items,
    )


# ------------------------------------------------------------ responder actions

def _load(db: Session, report_id: int) -> List[Report]:
    """The report, or for a hazard the whole group it belongs to."""
    row = db.get(Report, report_id)
    if row is None:
        raise ReportError(404, "Report not found.")
    return _hazard_group_of(db, row) if row.kind == HAZARD else [row]


def _require_open(rows: List[Report]) -> None:
    if rows[0].status not in OPEN:
        word = "marked false" if rows[0].status == FALSE else "resolved"
        raise ReportError(409, f"This report was already {word}.")


def _target(rows: List[Report]) -> str:
    return f"report:{rows[0].id}"


def take(db: Session, user: User, report_id: int, request: Optional[Request]) -> dict:
    rows = _load(db, report_id)
    _require_open(rows)
    first = rows[0]
    if first.status == BEING_HANDLED:
        if first.taken_by == user.name:  # a second tap: nothing to do
            return _item(rows)
        raise ReportError(409, f"{first.taken_by} is already handling this report.")
    now = _now()
    for r in rows:
        r.status, r.taken_by, r.taken_at, r.updated_at = BEING_HANDLED, user.name, now, now
    audit.record(db, user, "report.take", target=_target(rows), detail={"kind": first.kind}, request=request)
    db.commit()
    return _item(rows)


def resolve(db: Session, user: User, report_id: int, what_was_done: str, request: Optional[Request]) -> dict:
    rows = _load(db, report_id)
    _require_open(rows)
    now = _now()
    for r in rows:
        r.status, r.closed_by, r.closed_at, r.updated_at = RESOLVED, user.name, now, now
        r.resolution_note = what_was_done
    audit.record(db, user, "report.resolve", target=_target(rows),
                 detail={"kind": rows[0].kind, "what_was_done": what_was_done}, request=request)
    db.commit()
    return _item(rows)


def mark_false(db: Session, user: User, report_id: int, reason: str, request: Optional[Request]) -> dict:
    """
    Closes the report as false. Every phone in it gets one false report. A phone
    that reaches FALSE_REPORTS_BEFORE_BLOCK false reports (counted over the
    reports still kept) is blocked from sending reports.
    """
    rows = _load(db, report_id)
    _require_open(rows)
    now = _now()
    for r in rows:
        r.status, r.closed_by, r.closed_at, r.updated_at = FALSE, user.name, now, now
        r.false_reason = reason
    audit.record(db, user, "report.mark_false", target=_target(rows),
                 detail={"kind": rows[0].kind, "reason": reason}, request=request)

    db.flush()  # the count below must see the rows just changed (the session does not autoflush)
    for phone in sorted({r.phone_hash for r in rows}):
        old_block = db.query(BlockedPhone).filter(BlockedPhone.phone_hash == phone).first()
        if old_block is not None and _block_expired(old_block, now):
            _forgive(db, phone, now - timedelta(seconds=1))  # its block ran out: a fresh count, this report included
            db.delete(old_block)
        db.flush()
        q = db.query(Report).filter(Report.phone_hash == phone, Report.status == FALSE)
        forgiven = db.get(ForgivenPhone, phone)
        if forgiven is not None:  # unblocked before: only false reports since then count
            q = q.filter(Report.closed_at >= forgiven.since)
        strikes = q.count()
        if strikes >= config.FALSE_REPORTS_BEFORE_BLOCK and not is_blocked(db, phone):
            db.add(BlockedPhone(phone_hash=phone, false_reports=strikes))
            audit.record(db, user, "report.phone_blocked", target=f"phone:{phone[:8]}",
                         detail={"false_reports": strikes, "after_report": rows[0].id}, request=request)
    db.commit()
    return _item(rows)


def verify(db: Session, user: User, report_id: int, request: Optional[Request]) -> dict:
    rows = _load(db, report_id)
    if rows[0].kind != HAZARD:
        raise ReportError(422, "Only hazard reports can be verified.")
    _require_open(rows)
    if all(r.verified_at is not None for r in rows):  # a second tap: nothing to do
        return _item(rows)
    now = _now()
    for r in rows:
        r.verified_by, r.verified_at, r.updated_at = user.name, now, now
    audit.record(db, user, "report.verify", target=_target(rows), detail={"reports": len(rows)}, request=request)
    db.commit()
    return _item(rows)


# ------------------------------------------------------------ upgrading an existing database

# Columns added after the reports table first shipped: name -> SQL type.
_ADDED_REPORT_COLUMNS = {"category": "VARCHAR(40)", "people": "INTEGER", "can_move": "VARCHAR"}


def upgrade_report_columns(engine) -> List[str]:
    """
    Base.metadata.create_all makes missing tables but never adds a column to one
    that exists. This adds the part 2b columns to a reports table made by part 2,
    keeping every row (old reports simply have no category). Does nothing on a
    new or already upgraded database. Returns the columns it added.
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if not insp.has_table("reports"):
        return []
    have = {c["name"] for c in insp.get_columns("reports")}
    added = [name for name in _ADDED_REPORT_COLUMNS if name not in have]
    with engine.begin() as conn:
        for name in added:
            conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} {_ADDED_REPORT_COLUMNS[name]}"))
    return added


# ------------------------------------------------------------ deleting old reports

def purge_old_reports(db: Session, now: Optional[datetime] = None) -> int:
    """
    Delete reports sent more than REPORTS_KEEP_DAYS ago (open or closed). Blocked
    phones are kept: only the hashed ID and a count, and the block should
    outlive the reports. Returns how many reports were deleted and writes one
    audit entry (as "(system)") when it deleted any.
    """
    cutoff = (now or _now()) - timedelta(days=config.REPORTS_KEEP_DAYS)
    deleted = db.query(Report).filter(Report.created_at < cutoff).delete(synchronize_session=False)
    if deleted:
        audit.record(db, None, "report.purge", detail={"deleted": deleted, "older_than_days": config.REPORTS_KEEP_DAYS})
    db.commit()
    return deleted


def purge_on_startup() -> int:
    """Used when the server starts (see main.py). Never stops the server from starting."""
    db = SessionLocal()
    try:
        deleted = purge_old_reports(db)
        if deleted:
            print(f"Deleted {deleted} report(s) older than {config.REPORTS_KEEP_DAYS} days.")
        return deleted
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"Could not purge old reports: {e}")
        return 0
    finally:
        db.close()
