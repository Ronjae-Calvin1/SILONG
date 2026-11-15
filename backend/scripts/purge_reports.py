"""
Deletes help requests and hazard reports older than the retention time
(REPORTS_KEEP_DAYS in app/config.py, 30 days). The server also does this each
time it starts. Run it from the backend folder, for example once a day:

    py scripts/purge_reports.py

It uses the same database as the backend (DATABASE_URL, default typhoon.db in
this folder). Blocked phones are kept. Safe to run any time, as often as you like.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, report_service  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401  (makes sure every table is known)


def main() -> int:
    Base.metadata.create_all(bind=engine)  # makes the report tables if this is a new database
    db = SessionLocal()
    try:
        deleted = report_service.purge_old_reports(db)
        print(f"Deleted {deleted} report(s) older than {config.REPORTS_KEEP_DAYS} days.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
