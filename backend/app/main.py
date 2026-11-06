"""
Backbone: map slice + capacity/availability status (Batangas City facilities).
Facilities in SQLite -> FastAPI endpoints -> frontend fetches them.
Weather/AI modules still exist in the folder but aren't wired in yet.
"""
import json
import re
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from typing import List

from . import status_service
from .database import Base, engine, SessionLocal, get_db
from .models import Facility, StatusUpdate
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


def load_facilities() -> list:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return FACILITIES


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
    above) WITHOUT resetting it. Rows are matched on `key`, so a facility keeps
    the same numeric id across restarts and re-fetches, and its status history
    stays attached to the right place.

      - new key      -> inserted
      - known key    -> name/coordinates/address/contact/notes refreshed
      - missing key  -> facility removed (the data file no longer lists it),
                        together with its status history
    """
    db = SessionLocal()
    try:
        wanted = {}
        for f in load_facilities():
            key = facility_key(f)
            if key in wanted:  # same key twice in the file: keep the first
                continue
            wanted[key] = f

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
    """All facilities, each with its latest status (or null) attached."""
    latest = status_service.latest_status_by_facility(db)
    out = []
    for f in db.query(Facility).order_by(Facility.id).all():
        item = FacilityOut.model_validate(f)  # `status` is empty on the row itself
        item.status = latest.get(f.id)
        out.append(item)
    return out


def _get_facility_or_404(db: Session, facility_id: int) -> Facility:
    facility = db.get(Facility, facility_id)
    if facility is None:
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

    try:
        validate_for_facility_type(payload, facility.type)
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
        status=payload.status,
        people_inside=payload.people_inside,
        max_capacity=payload.max_capacity,
        resources=json.dumps(payload.resources) if payload.resources else None,
        note=payload.note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return status_service.to_status_out(row)


@app.get("/api/facilities/{facility_id}/status/history", response_model=List[StatusOut])
def status_history(
    facility_id: int,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Newest first. Simple view for debugging and later use."""
    _get_facility_or_404(db, facility_id)
    return status_service.history(db, facility_id, limit)
