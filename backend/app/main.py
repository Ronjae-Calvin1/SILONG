"""
Backbone: map slice + capacity/availability status (Batangas City facilities)
+ evacuation center manager (add / soft remove / restore, see evac_routes.py).
Facilities in SQLite -> FastAPI endpoints -> frontend fetches them.
Weather/AI modules still exist in the folder but aren't wired in yet.
"""
import json
import re
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from typing import List

from . import evac_service, status_service
from .database import Base, engine, SessionLocal, get_db
from .evac_routes import router as evac_router
from .models import Facility, StatusUpdate, UserEvacuationCenter
from .rate_limit import limiter
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
# Creates any table that does not exist yet (including the evacuation center
# manager tables on an existing database) and leaves existing tables untouched,
# so nobody has to delete the database file.
Base.metadata.create_all(bind=engine)


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
    API just hides them.
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

app = FastAPI(title="SILONG API — map and status")
app.include_router(evac_router)

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
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/facilities", response_model=List[FacilityOut])
def list_facilities(db: Session = Depends(get_db)):
    """
    All facilities from every source (osm / manual / user), minus removed
    evacuation centers. Each has its latest status (or null) and, for
    evacuation centers, the capacity fields.
    """
    latest = status_service.latest_status_by_facility(db)
    status_max = status_service.latest_max_capacity_by_facility(db)
    users = {f"user:{u.id}": u for u in db.query(UserEvacuationCenter).all()}
    removed = evac_service.removed_keys(db)
    return [
        evac_service.to_facility_out(f, latest.get(f.id), users.get(f.key), status_max.get(f.id))
        for f in db.query(Facility).order_by(Facility.id).all()
        if f.key not in removed
    ]


def _get_facility_or_404(db: Session, facility_id: int) -> Facility:
    facility = db.get(Facility, facility_id)
    if facility is None or evac_service.active_removal(db, facility.key):
        raise HTTPException(status_code=404, detail="Facility not found.")
    return facility


@app.post("/api/facilities/{facility_id}/status", response_model=StatusOut, status_code=201)
def submit_status(
    facility_id: int,
    payload: StatusIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Add a status update (kept as history). Returns the new latest status."""
    facility = _get_facility_or_404(db, facility_id)

    # The capacity rule (people_inside >= max_capacity -> full) lives in
    # status_service.resolve_status; nothing else decides it.
    try:
        validate_for_facility_type(payload, facility.type)
        user_row = evac_service.user_row_for(db, facility.key)
        resolved = status_service.resolve_status(
            payload,
            status_service.effective_max_capacity(db, facility.id, user_row.max_capacity if user_row else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Rate limit after validation, so a mistyped form does not use up the allowance.
    ip = request.client.host if request.client else "unknown"
    hit = limiter.check(ip, facility_id)
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
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    out = status_service.to_status_out(row)
    out.message = resolved.message
    return out


@app.get("/api/facilities/{facility_id}/status/history", response_model=List[StatusOut])
def status_history(
    facility_id: int,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Newest first. Simple view for debugging and later use."""
    _get_facility_or_404(db, facility_id)
    return status_service.history(db, facility_id, limit)
