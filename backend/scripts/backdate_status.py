"""
Test helper for the "May be outdated" rule: moves the LATEST status update of
one facility back in time, so you can see how an old status looks.

Run from the backend folder (standard library only, the backend can keep running):

    py scripts/backdate_status.py 3 --hours 7      # facility 3: latest update is now 7 h old
    py scripts/backdate_status.py 3 --minutes 15   # make it look 15 minutes old
    py scripts/backdate_status.py --list           # show each facility's latest update

Then refresh the page (or wait up to a minute: the page re-checks on its own).
Use --db to point at a different database file (default: typhoon.db).
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

p = argparse.ArgumentParser()
p.add_argument("facility_id", nargs="?", type=int)
p.add_argument("--hours", type=float, default=0)
p.add_argument("--minutes", type=float, default=0)
p.add_argument("--db", default="typhoon.db")
p.add_argument("--list", action="store_true")
args = p.parse_args()

con = sqlite3.connect(args.db)

if args.list or args.facility_id is None:
    rows = con.execute(
        """SELECT f.id, f.name, s.status, s.created_at FROM facilities f
           JOIN status_updates s ON s.id = (SELECT MAX(id) FROM status_updates WHERE facility_id = f.id)
           ORDER BY f.id"""
    ).fetchall()
    print("id  status       latest update (UTC)         name")
    for fid, name, status, at in rows:
        print(f"{fid:<3} {status:<12} {at}  {name}")
    if not rows:
        print("(no status updates yet)")
    raise SystemExit(0)

delta = timedelta(hours=args.hours, minutes=args.minutes)
if delta <= timedelta(0):
    raise SystemExit("Give --hours and/or --minutes (greater than 0).")

row = con.execute(
    "SELECT id FROM status_updates WHERE facility_id = ? ORDER BY id DESC LIMIT 1", (args.facility_id,)
).fetchone()
if row is None:
    raise SystemExit(f"Facility {args.facility_id} has no status update yet. Submit one first.")

# Same format SQLAlchemy writes: naive UTC.
new_time = (datetime.now(timezone.utc) - delta).replace(tzinfo=None)
con.execute("UPDATE status_updates SET created_at = ? WHERE id = ?", (new_time.isoformat(sep=" "), row[0]))
con.commit()
print(f"Latest update of facility {args.facility_id} now dated {new_time:%Y-%m-%d %H:%M:%S} UTC.")
