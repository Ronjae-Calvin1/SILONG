"""
Deletes evacuation centers that were removed more than REMOVED_CENTERS_KEEP_DAYS days ago
(app/config.py, 30 days), together with their status history, and places that were rejected that
long ago. The server also does this each time it starts. Run it from the backend folder, for
example once a day:

    py scripts/purge_removed_centers.py

It uses the same database as the backend (DATABASE_URL, default typhoon.db in this folder).
A center that was restored is never touched. A center that comes from a data file (OpenStreetMap
or manual_facilities.json) is noted in the deleted_facilities table so the next start does not
read it from the file again. Safe to run any time, as often as you like.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, place_service  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401  (makes sure every table is known)


def main() -> int:
    Base.metadata.create_all(bind=engine)  # makes the tables if this is a new database
    place_service.upgrade_place_columns(engine)  # and adds the newer columns to an older database
    db = SessionLocal()
    try:
        deleted = place_service.purge_removed_centers(db)
        print(f"Deleted {deleted} removed or rejected place(s) older than {config.REMOVED_CENTERS_KEEP_DAYS} days.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
