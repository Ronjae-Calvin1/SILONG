"""
Backbone: map slice + capacity/availability status (Batangas City facilities)
+ evacuation center manager (add as pending, staff approve / remove / restore, see evac_routes.py
  and place_routes.py; the rules are in place_service.py)
+ staff accounts, roles and the audit log (see account_routes.py)
+ help requests and hazard reports (see report_routes.py)
+ weather, advisories and emergency numbers (see content_routes.py)
+ the chatbot placeholder (see chat_routes.py and chat_service.py)
+ phone blocks (ops_routes.py) and the scheduled cleanup (maintenance.py).
Facilities in SQLite -> FastAPI endpoints -> frontend fetches them.
"""
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from typing import List, Optional

from . import accounts, audit, content_service, evac_service, place_service, report_service, status_service
from .account_routes import router as account_router
from .auth import optional_staff
from .chat_routes import router as chat_router
from .content_routes import router as content_router
from .database import Base, engine, SessionLocal, get_db
from .evac_routes import router as evac_router
from .maintenance import scheduler
from .models import DeletedFacility, Facility, StatusUpdate, User, UserEvacuationCenter
from .ops_routes import router as ops_router
from .place_routes import router as place_router
from .rate_limit import limiter
from .report_routes import optional_phone, router as report_router
from .schemas import FacilityOut, StatusIn, StatusOut, validate_for_facility_type


def _drop_legacy_facilities_table():
    """
    Older databases have a facilities table without the stable `key` column.
    That table was rebuilt from the data files on every start, so dropping it
    loses nothing (status updates did not exist yet).
    """
    insp = inspect(engine)
    if insp.has_table("facilities") and "key" not in {c["name"] for c in insp.get_columns("facilities")}:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE facilities"))


_drop_legacy_facilities_table()
# The official-sources and emergency-numbers tables get their starting rows (PAGASA, NDRRMC,
# Batangas City CDRRMO; 911) only when they are first created, so this runs before create_all.
content_service.prepare_tables(engine)
# Creates any table that does not exist yet (including the evacuation center
# manager tables on an existing database) and leaves existing tables untouched,
# so nobody has to delete the database file.
Base.metadata.create_all(bind=engine)
# create_all does not add columns to a table that already exists: add the newer report columns
# and the part 3 place and status columns. This must stay before sync_facilities() below, which
# reads those columns.
report_service.upgrade_report_columns(engine)
place_service.upgrade_place_columns(engine)


# Real hospitals in Batangas City, from the city government's official
# hospitals page. Coordinates are APPROXIMATE (Batangas Medical Center uses the
# Wikipedia point; the rest come from Google Maps links on the city page, which
# give the map view center, not the exact pin). Verify each one by
# right-clicking the exact pin in Google Maps before the final submission.
# Clinics and evacuation centers are not seeded yet: they need the official
# list from the Batangas City CDRRMO / barangay halls.
FACILITIES = [
    dict(name="Batangas Medical Center", type="hospital",
         latitude=13.76698, longitude=121.06678,
         address="Bihi Road, Kumintang Ibaba, Batangas City",
         contact="(043) 723-0165"),
    dict(name="Golden Gate General Hospital", type="hospital",
         latitude=13.7538, longitude=121.0590,
         address="P. Prieto St., Batangas City",
         contact="(043) 723-3011",
         notes="Approximate coordinates - verify."),
    dict(name="Jesus of Nazareth Hospital", type="hospital",
         latitude=13.7548, longitude=121.0647,
         address="Gov. Antonio Carpio Rd., Gulod Labac, Batangas City",
         contact="(043) 723-2918",
         notes="Approximate coordinates - verify."),
    dict(name="St. Patrick's Hospital Medical Center", type="hospital",
         latitude=13.7527, longitude=121.0535,
         address="Lopez Jaena, Batangas City",
         contact="(043) 723-7089",
         notes="Approximate coordinates - verify."),
    dict(name="United Doctors of St. Camillus de Lellis Hospital", type="hospital",
         latitude=13.7814, longitude=121.0557,
         address="Diversion Road, Batangas City",
         notes="Approximate coordinates - verify."),
]


# If scripts/fetch_facilities.py has been run, its OpenStreetMap results are
# used instead of the hardcoded FACILITIES list above.
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "facilities.json"
# Places added by hand. The fetch script also merges this file into
# facilities.json; both are read here so an entry works without re-running it.
# An entry present in both gets the same key and is kept once.
MANUAL_FILE = DATA_FILE.parent / "manual_facilities.json"
_FACILITY_FIELDS = ("name", "type", "latitude", "longitude", "address", "contact", "notes")


def load_manual_facilities() -> list:
    if not MANUAL_FILE.exists():
        return []
    try:
        rows = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"Ignoring {MANUAL_FILE.name}: not valid JSON ({e})")
        return []
    items = []
    for row in rows:
        if not all(k in row for k in ("name", "type", "latitude", "longitude")):
            print(f"Skipping manual entry missing name/type/latitude/longitude: {row}")
            continue
        item = {k: row.get(k) for k in _FACILITY_FIELDS}  # drops unknown fields
        item["notes"] = item["notes"] or "Added manually"
        items.append(item)
    return items


def load_facilities() -> list:
    base = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else FACILITIES
    return base + load_manual_facilities()


_OSM_REF = re.compile(r"OpenStreetMap\s+(node|way|relation)/(\d+)")


def facility_key(f: dict) -> str:
    """
    A stable identity for a facility that does not depend on its position in
    the file. Facilities fetched from OpenStreetMap carry their OSM reference in
    `notes` ("Source: OpenStreetMap way/123"), which is unique and permanent.
    Anything else (manual entries, the hardcoded fallback) falls back to
    type + name, so names must be unique within a type for those.
    """
    m = _OSM_REF.search(f.get("notes") or "")
    if m:
        return f"osm:{m.group(1)}/{m.group(2)}"
    name = re.sub(r"[^a-z0-9]+", "-", f["name"].lower()).strip("-")
    return f"manual:{f['type']}:{name}"


def sync_facilities():
    """
    Bring the facilities table in line with data/facilities.json (or the list
    above), manual_facilities.json and the user-added centers WITHOUT resetting
    it. Rows are matched on `key`, so a facility keeps the same numeric id across
    restarts and re-fetches, and its status history stays attached to the right
    place.

      - new key      -> inserted
      - known key    -> name/coordinates/address/contact/notes refreshed
      - missing key  -> facility removed (no source lists it any more),
                        together with its status history

    User-added centers (key "user:<n>") are listed from their own table, so they
    are never swept away here. Soft-removed centers stay in the table too: the
    API just hides them. A center from a data file that was deleted for good
    (place_service.delete_for_good / the purge) is on the deleted_facilities list
    and is not read from the file again.
    """
    db = SessionLocal()
    try:
        wanted = {}
        for f in load_facilities():
            key = facility_key(f)
            if key in wanted:  # same key twice in the file: keep the first
                continue
            wanted[key] = f

        for u in db.query(UserEvacuationCenter).all():
            wanted[f"user:{u.id}"] = evac_service.user_center_facility_fields(u)

        deleted = {key for (key,) in db.query(DeletedFacility.key).all()}
        for key in deleted:
            wanted.pop(key, None)

        existing = {row.key: row for row in db.query(Facility).all()}

        for key, f in wanted.items():
            row = existing.get(key)
            if row is None:
                db.add(Facility(key=key, **f))
            else:
                for field, value in f.items():
                    setattr(row, field, value)

        for key, row in existing.items():
            if key not in wanted:
                db.query(StatusUpdate).filter(StatusUpdate.facility_id == row.id).delete()
                db.delete(row)
        db.commit()
    finally:
        db.close()


sync_facilities()
# Delete reports older than the retention time (see config.REPORTS_KEEP_DAYS).
report_service.purge_on_startup()
# Delete removed centers (and rejected places) kept longer than config.REMOVED_CENTERS_KEEP_DAYS.
place_service.purge_on_startup()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Starts the scheduled cleanup with the server and stops it cleanly on shutdown (maintenance.py)."""
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(title="SILONG API — map and status", lifespan=lifespan)
app.include_router(evac_router)
app.include_router(account_router)
app.include_router(report_router)
app.include_router(place_router)
app.include_router(content_router)
app.include_router(chat_router)
app.include_router(ops_router)

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """
    FastAPI's normal 422 (type / loc / msg), without the `input` it echoes back.
    A request body can contain NaN or Infinity, which is not valid JSON, so
    echoing it made the error response itself crash into a 500.
    """
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],  # lets the browser read the audit-log total from another origin
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/facilities", response_model=List[FacilityOut])
def list_facilities(phone: Optional[str] = Depends(optional_phone), db: Session = Depends(get_db)):
    """
    All facilities from every source (osm / manual / user), minus removed
    evacuation centers and places that are not approved. Each has its latest
    status (or null, with `source` and `source_label` saying who reported it) and,
    for evacuation centers, the capacity fields. The one extra: with an X-Phone-Id
    header, the places that phone added and that still wait for approval are in
    the list too, with "approval_status": "pending".
    """
    latest = status_service.latest_status_by_facility(db)
    status_max = status_service.latest_max_capacity_by_facility(db)
    users = {f"user:{u.id}": u for u in db.query(UserEvacuationCenter).all()}
    hidden = evac_service.hidden_keys(db, phone)
    return [
        evac_service.to_facility_out(f, latest.get(f.id), users.get(f.key), status_max.get(f.id))
        for f in db.query(Facility).order_by(Facility.id).all()
        if f.key not in hidden
    ]


def _get_facility_or_404(db: Session, facility_id: int, phone: Optional[str] = None) -> Facility:
    """The facility, or 404 when this caller may not see it (removed, rejected, or somebody else's pending place)."""
    facility = evac_service.get_visible_facility(db, facility_id, phone)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found.")
    return facility


@app.post("/api/facilities/{facility_id}/status", response_model=StatusOut, status_code=201)
def submit_status(
    facility_id: int,
    payload: StatusIn,
    request: Request,
    staff: Optional[User] = Depends(optional_staff),
    phone: Optional[str] = Depends(optional_phone),
    db: Session = Depends(get_db),
):
    """
    Add a status update (kept as history). Returns the new latest status.

    Anyone can send it and it is saved as "Reported by a user". When a signed-in responder or
    Super admin sends it (Authorization: Bearer ...), it is saved as "Confirmed by official" with
    their name, and it can set the maximum capacity. A user's report cannot change a maximum
    capacity an official has set. A place that is still waiting for approval accepts updates only
    from the phone that added it (X-Phone-Id).
    """
    facility = _get_facility_or_404(db, facility_id, phone)
    official = staff is not None and accounts.ROLE_RANK.get(staff.role, 0) >= accounts.ROLE_RANK[accounts.RESPONDER]

    # The capacity rule (people_inside >= max_capacity -> full) lives in
    # status_service.resolve_status; nothing else decides it.
    try:
        validate_for_facility_type(payload, facility.type)
        user_row = evac_service.user_row_for(db, facility.key)
        resolved = status_service.resolve_status(
            payload,
            status_service.effective_max_capacity(db, facility.id, user_row.max_capacity if user_row else None),
            locked_max=None if official else status_service.official_max_capacity(db, facility.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Rate limit after validation, so a mistyped form does not use up the allowance.
    # Signed-in staff are not limited: they are known, and in a storm they update many places.
    ip = request.client.host if request.client else "unknown"
    hit = None if official else limiter.check(ip, facility_id)
    if hit:
        scope, wait = hit
        if scope == "place":
            msg = f"You just updated this place. Please wait {wait} seconds before sending another update."
        else:
            minutes = max(1, round(wait / 60))
            msg = f"Too many updates from your connection. Please try again in about {minutes} minute(s)."
        raise HTTPException(status_code=429, detail=msg, headers={"Retry-After": str(wait)})

    row = StatusUpdate(
        facility_id=facility.id,
        status=resolved.status,
        people_inside=resolved.people_inside,
        max_capacity=resolved.max_capacity,
        resources=json.dumps(payload.resources) if payload.resources else None,
        note=payload.note,
        source=status_service.OFFICIAL if official else status_service.USER,
        kind=status_service.REPORT,
        changed_by=staff.name if official else None,
    )
    db.add(row)
    if official:
        audit.record(
            db, staff, "status.update", target=f"facility:{facility.id} ({facility.name})",
            detail={"status": resolved.status, "people_inside": resolved.people_inside, "max_capacity": resolved.max_capacity},
            request=request,
        )
    db.commit()
    db.refresh(row)
    out = status_service.to_status_out(row)
    out.message = resolved.message
    return out


@app.get("/api/facilities/{facility_id}/status/history", response_model=List[StatusOut])
def status_history(
    facility_id: int,
    limit: int = Query(10, ge=1, le=100),
    phone: Optional[str] = Depends(optional_phone),
    db: Session = Depends(get_db),
):
    """Newest first. Simple view for debugging and later use. (Staff see overrides and capacity corrections too, with names, in /api/responder/facilities/{id}/status-history.)"""
    _get_facility_or_404(db, facility_id, phone)
    return status_service.history(db, facility_id, limit)
