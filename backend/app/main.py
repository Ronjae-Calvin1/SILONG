"""
Backbone: map slice only (Batangas City facilities).
Facilities in SQLite -> one FastAPI endpoint -> frontend fetches it.
Weather/AI modules still exist in the folder but aren't wired in yet.
"""
import json
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from .database import Base, engine, SessionLocal, get_db
from .models import Facility
from .schemas import FacilityOut

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


def seed_facilities():
    """
    Reset the facilities table from data/facilities.json (or the list above)
    on every startup. Fine for the backbone since the data lives in files.
    Once facilities can be edited through the app, only seed an empty table.
    """
    db = SessionLocal()
    try:
        db.query(Facility).delete()
        db.add_all([Facility(**f) for f in load_facilities()])
        db.commit()
    finally:
        db.close()


seed_facilities()

app = FastAPI(title="Typhoon Prep API — map slice")

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
    return db.query(Facility).all()
