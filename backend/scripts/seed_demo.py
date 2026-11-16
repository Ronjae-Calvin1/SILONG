"""
Fills a database with clearly marked DEMO data, for building and testing screens.

    py scripts/seed_demo.py --db demo.db                 # a separate file (recommended)
    py scripts/seed_demo.py --db demo.db --with-demo-staff
    py scripts/seed_demo.py --force                      # the real database (typhoon.db): think twice

What it makes (everything says DEMO in its text, and the fake phones are "demo-phone-..."):
  - help requests (new, being handled, resolved) and hazard reports from different fake phones:
    a hazard reported by 3 phones (shows as Unconfirmed), a verified hazard, and a hazard with one report
  - evacuation centers: approved ones (one with a status) and pending ones (one is a possible duplicate)
  - advisories (one pinned, one from an official source)
  - with --with-demo-staff only: a demo responder and a demo Super admin. The script PRINTS their
    passwords once, when it makes them.

Safety:
  - It prints which database it uses first.
  - It refuses to run on the default real database (typhoon.db) or on any database that is not a
    SQLite file, unless you add --force.
  - Run it twice and nothing is added twice: what already exists is left as it is.
  - It uses DATABASE_URL (or backend/.env) when --db is not given.
"""
import argparse
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_DB_FILE = "typhoon.db"


def _database_url(db_arg):
    """The URL this run will use. Loads backend/.env (through config) so DATABASE_URL set there counts."""
    if db_arg:
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(db_arg).resolve()}"
    from app import config  # noqa: F401  (loads backend/.env without overriding the real environment)
    return os.getenv("DATABASE_URL", f"sqlite:///./{DEFAULT_DB_FILE}")


def _describe(url):
    """(text to print without any password, is_real_database)"""
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    shown = parsed.render_as_string(hide_password=True)
    if parsed.get_backend_name() != "sqlite":
        return shown, True  # not a local file: assume it is a real server
    name = Path(parsed.database or "").name
    return shown, name == DEFAULT_DB_FILE


def _phone(n):
    return f"demo-phone-{n:04d}-silong-seed"  # 16 to 64 letters, digits, - or _


# Positions are far enough apart (> HAZARD_MERGE_METERS) that the three hazards stay separate.
HAZARD_A = (13.7565, 121.0583)  # 3 phones
HAZARD_B = (13.7610, 121.0650)  # verified
HAZARD_C = (13.7500, 121.0500)  # 1 phone


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fill a database with DEMO data for building screens.")
    ap.add_argument("--db", help="SQLite file to use (made if missing). Without it, DATABASE_URL or typhoon.db.")
    ap.add_argument("--force", action="store_true", help="allow the real database (typhoon.db) or a non-SQLite one")
    ap.add_argument("--with-demo-staff", action="store_true", help="also make a demo responder and a demo Super admin")
    args = ap.parse_args(argv)

    url = _database_url(args.db)
    shown, is_real = _describe(url)
    print(f"Database: {shown}")
    if is_real and not args.force:
        print("Refusing to put DEMO data in the real database. Use --db demo.db for a separate file,")
        print("or add --force if you really mean this database. Nothing was changed.")
        return 2

    # Only now load the app: importing it creates the tables and fills in the map data.
    from app import main as _app  # noqa: F401  (makes every table and the map data)
    from app import accounts, audit, evac_service, report_service
    from app.database import SessionLocal
    from app.models import Advisory, Facility, Report, StatusUpdate, User, UserEvacuationCenter
    from app.schemas import EvacCenterIn

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    made = {"reports": 0, "places": 0, "advisories": 0, "accounts": 0}
    db = SessionLocal()
    try:
        # ---- reports ----
        def report(kind, phone_n, lat, lng, note, **kw):
            phone = report_service.hash_phone_id(_phone(phone_n))
            exists = db.query(Report).filter(Report.phone_hash == phone, Report.kind == kind, Report.note == note).first()
            if exists:
                return exists
            row, created = report_service.create_report(
                db, kind, lat, lng, kw.pop("contact", None), note, phone, "127.0.0.1", **kw)
            db.flush()
            made["reports"] += 1 if created else 0
            return row

        report("help", 1, 13.7545, 121.0598, "DEMO help request: new", contact="DEMO 0900-000-0001",
               category="Trapped", people=3, can_move="no")
        h2 = report("help", 2, 13.7580, 121.0610, "DEMO help request: being handled", contact="DEMO 0900-000-0002",
                    category="Medical", people=1, can_move="unsure")
        h3 = report("help", 3, 13.7620, 121.0540, "DEMO help request: resolved", contact="DEMO 0900-000-0003",
                    category="Food or water", people=5, can_move="yes")
        if h2.status == report_service.NEW:
            h2.status, h2.taken_by, h2.taken_at, h2.updated_at = report_service.BEING_HANDLED, "DEMO seed", now, now
        if h3.status == report_service.NEW:
            h3.status, h3.taken_by, h3.closed_by, h3.closed_at, h3.updated_at = report_service.RESOLVED, "DEMO seed", "DEMO seed", now, now
            h3.resolution_note = "DEMO: a team brought supplies"
        for n in (4, 5, 6):  # one hazard, three different phones
            report("hazard", n, HAZARD_A[0], HAZARD_A[1], f"DEMO hazard with 3 phones (phone {n - 3})", category="Flooded road")
        hb = report("hazard", 7, HAZARD_B[0], HAZARD_B[1], "DEMO verified hazard", category="Fallen tree")
        if hb.verified_at is None:
            for r in report_service._hazard_group_of(db, hb):
                r.verified_by, r.verified_at, r.updated_at = "DEMO seed", now, now
            audit.record(db, "DEMO seed script", "report.verify", target=f"report:{hb.id}", detail={"demo": True})
        report("hazard", 8, HAZARD_C[0], HAZARD_C[1], "DEMO hazard with one report", category="Power line down")
        db.commit()

        # ---- places ----
        def place(name, lat, lng, approved, phone_n=9, barangay="DEMO Barangay", capacity=150):
            if db.query(UserEvacuationCenter).filter(UserEvacuationCenter.name == name).first():
                return db.query(Facility).filter(Facility.name == name).first()
            payload = EvacCenterIn(name=name, center_type="temporary", barangay=barangay, address="DEMO street",
                                   contact="DEMO 0900-000-0009", max_capacity=capacity, latitude=lat, longitude=lng,
                                   note="DEMO place, not real")
            f = evac_service.create_center(db, payload, phone_hash=report_service.hash_phone_id(_phone(phone_n)))
            row = evac_service.user_row_for(db, f.key)
            if approved:
                row.approval_status, row.reviewed_by, row.reviewed_at = "approved", "DEMO seed", now
            made["places"] += 1
            db.flush()
            return f

        a = place("DEMO Alangilan Gymnasium", 13.7640, 121.0700, True)
        place("DEMO Barangay Hall Shelter", 13.7470, 121.0610, True)
        place("DEMO Covered Court (waiting)", 13.7700, 121.0450, False, phone_n=10)
        place("DEMO Church Hall (waiting)", 13.7400, 121.0700, False, phone_n=11)
        # a pending place with the same name 10 m from an approved one: shows the "possible duplicate" flag
        dup_phone = report_service.hash_phone_id(_phone(12))
        if not db.query(UserEvacuationCenter).filter(UserEvacuationCenter.phone_hash == dup_phone).first():
            f = evac_service.create_center(db, EvacCenterIn(
                name="DEMO Alangilan Gymnasium", center_type="temporary", barangay="DEMO Barangay", address="DEMO street",
                contact="DEMO 0900-000-0012", max_capacity=150, latitude=13.76405, longitude=121.07005, note="DEMO duplicate"),
                phone_hash=dup_phone)
            made["places"] += 1
        db.flush()
        if a is not None and not db.query(StatusUpdate).filter(StatusUpdate.facility_id == a.id).first():
            db.add(StatusUpdate(facility_id=a.id, status="almost_full", people_inside=120, max_capacity=150,
                                note="DEMO status", source="user", kind="report"))
        db.commit()

        # ---- advisories ----
        for title, source, pinned, days in (
            ("DEMO: Sample typhoon warning (not real)", "PAGASA", True, 0),
            ("DEMO: Sample road closure notice (not real)", "DEMO source", False, 1),
            ("DEMO: Sample class suspension notice (not real)", "DEMO source", False, 2),
        ):
            if not db.query(Advisory).filter(Advisory.title == title).first():
                db.add(Advisory(title=title, details="DEMO text for building screens. This is not a real advisory.",
                                source=source, source_url="https://example.com/demo", pinned=pinned,
                                created_at=now - timedelta(days=days), created_by="DEMO seed"))
                made["advisories"] += 1
        db.commit()

        # ---- demo staff (only on request) ----
        if args.with_demo_staff:
            for name, role in (("Demo Responder", "responder"), ("Demo Super Admin", "super_admin")):
                if db.query(User).filter(User.name_key == accounts.normalize_name(name)).first():
                    print(f"Account '{name}' already exists. Its password is not shown again.")
                    continue
                password = secrets.token_urlsafe(12)
                accounts.create_user(db, name, password, role, actor="DEMO seed script")
                made["accounts"] += 1
                print(f"Made account '{name}' ({role}) with password: {password}")
    finally:
        db.close()

    print("Done. Added: " + ", ".join(f"{n} {k}" for k, n in made.items()) + ". (Anything that already existed was left alone.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
