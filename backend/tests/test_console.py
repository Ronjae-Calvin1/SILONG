"""
Update 14 checks: the Admin console gaps (Mine and release, badge counts, my activity, contact settings,
emergency number categories, distance and polling).

    py tests/test_console.py

Own temporary database, like the other test files.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="silong-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "1000"
os.environ["REPORT_PHONE_COOLDOWN_SECONDS"] = "0"
os.environ["REPORT_PHONE_MAX"] = "1000"
os.environ["REPORT_IP_MAX"] = "1000"
os.environ["REPORT_READ_MAX"] = "1000"
os.environ["MANAGE_MAX_ACTIONS"] = "100000"
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, console_service, content_service  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Report  # noqa: E402

client = TestClient(app)
PASSWORD = "correct horse 1"
HOME = (13.7565, 121.0583)
NEAR = (13.7610, 121.0583)  # about 500 m north of HOME
FAR = (13.7790, 121.0583)  # about 2.5 km north of HOME
NO_AUTH = {}


def make_user(name):
    db = SessionLocal()
    try:
        return accounts.create_user(db, name, PASSWORD, actor="test setup").id
    finally:
        db.close()


def auth(name):
    r = client.post("/api/auth/sign-in", json={"name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


make_user("Ana Admin")
make_user("Ben Admin")
HA, HB = auth("Ana Admin"), auth("Ben Admin")
_n = iter(range(1, 100_000))


def phone():
    return f"phone-test-{next(_n):08d}-abcdef"


def send(kind, where=HOME, who=None, **extra):
    body = {"kind": kind, "category": "Trapped" if kind == "help" else "Flooded road",
            "latitude": where[0], "longitude": where[1], **extra}
    if kind == "help":
        body.setdefault("contact", "0917 000 0000")
    r = client.post("/api/reports", headers={"X-Phone-Id": who or phone()}, json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def act(headers, rid, what, **body):
    return client.post(f"/api/admin/reports/{rid}/{what}", headers=headers, json=body or None)


def listing(headers=HA, **params):
    r = client.get("/api/admin/reports", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def audit_rows(action=None):
    db = SessionLocal()
    try:
        q = db.query(AuditLog)
        if action:
            q = q.filter(AuditLog.action == action)
        return [(a.actor_name, a.action, a.target) for a in q.order_by(AuditLog.id).all()]
    finally:
        db.close()


# ---------------------------------------------------------------- 1. Mine and release

def test_taken_reports_show_the_admins_name_and_the_mine_filter_and_flag():
    r1, r2 = send("help"), send("help")
    assert act(HA, r1, "take").status_code == 200
    assert act(HB, r2, "take").status_code == 200
    items = {i["id"]: i for i in listing(HA)["items"]}
    assert items[r1]["taken_by"] == "Ana Admin" and items[r1]["is_mine"] is True
    assert items[r2]["taken_by"] == "Ben Admin" and items[r2]["is_mine"] is False
    mine_ids = [i["id"] for i in listing(HA, mine=True)["items"]]
    assert r1 in mine_ids and r2 not in mine_ids
    assert all(i["is_mine"] for i in listing(HA, mine=True)["items"])
    # The actions answer with the same flag.
    assert act(HA, r1, "take").json()["is_mine"] is True  # a second tap
    for rid in (r1, r2):
        assert act(HA if rid == r1 else HB, rid, "resolve", what_was_done="Helped on site").status_code == 200
    assert r1 not in [i["id"] for i in listing(HA, mine=True)["items"]]  # open only by default
    closed_mine = [i["id"] for i in listing(HA, mine=True, include_closed=True)["items"]]
    assert r1 in closed_mine and r2 not in closed_mine


def test_release_gives_the_report_back_to_new_and_is_audited():
    rid = send("help")
    assert act(HA, rid, "take").status_code == 200
    assert act(HB, rid, "release").status_code == 409  # not yours
    item = act(HA, rid, "release").json()
    assert item["status"] == "new" and item["taken_by"] is None and item["is_new_help"] is True and item["is_mine"] is False
    assert listing(HA)["has_new_help"] is True
    assert act(HA, rid, "release").status_code == 200  # safe to call twice
    assert audit_rows("report.release").count(("Ana Admin", "report.release", f"report:{rid}")) == 1  # the second call logs nothing
    assert act(HB, rid, "take").json()["taken_by"] == "Ben Admin"  # somebody else can take it now
    assert act(HB, rid, "resolve", what_was_done="Helped on site").status_code == 200
    assert act(HB, rid, "release").status_code == 409  # closed
    assert act(HB, 999_999, "release").status_code == 404


def test_release_works_for_a_hazard_group():
    a, b = send("hazard"), None
    b = send("hazard", where=(HOME[0] + 0.0003, HOME[1]))  # joins the same hazard
    assert act(HA, a, "take").status_code == 200
    item = act(HA, b, "release").json()
    assert item["status"] == "new" and item["taken_by"] is None and item["report_count"] == 2
    db = SessionLocal()
    try:
        rows = db.query(Report).filter(Report.group_id == a).all()
        assert len(rows) == 2 and all(r.status == "new" and r.taken_by is None for r in rows)
    finally:
        db.close()
    assert act(HA, a, "mark-false", reason="test hazard").status_code == 200


# ---------------------------------------------------------------- 7. distance and since

def test_distance_is_added_when_a_position_is_sent():
    rid = send("help", where=NEAR)
    plain = {i["id"]: i for i in listing()["items"]}
    assert plain[rid]["distance_m"] is None
    items = {i["id"]: i for i in listing(latitude=HOME[0], longitude=HOME[1])["items"]}
    assert 400 < items[rid]["distance_m"] < 600
    assert client.get("/api/admin/reports", headers=HA, params={"latitude": 13.7}).status_code == 422
    assert client.get("/api/admin/reports", headers=HA, params={"longitude": 121.0}).status_code == 422
    assert client.get("/api/admin/reports", headers=HA, params={"latitude": 95, "longitude": 121.0}).status_code == 422
    assert act(HA, rid, "mark-false", reason="test report").status_code == 200


def test_since_returns_only_what_changed_and_includes_closed_ones():
    first = listing()
    stamp = first["server_time"]
    assert first["since"] is None
    quiet = listing(since=stamp)
    assert quiet["items"] == [] and quiet["since"] is not None
    old = send("help")
    stamp = listing()["server_time"]
    new = send("help", where=FAR)
    changed = listing(since=stamp)
    ids = [i["id"] for i in changed["items"]]
    assert ids == [new] and old not in ids
    assert changed["new_help_count"] >= 2  # the alert counts cover everything, not just the changes
    # A report that another Admin closes shows up in the next poll even though closed ones are hidden normally.
    stamp = changed["server_time"]
    assert act(HB, old, "mark-false", reason="test report").status_code == 200
    polled = listing(since=stamp)
    assert [i["id"] for i in polled["items"]] == [old] and polled["items"][0]["status"] == "false"
    assert old not in [i["id"] for i in listing()["items"]]
    # kind and mine still apply; a time with a zone and a bad time are handled.
    assert listing(since=stamp, kind="hazard")["items"] == []
    assert listing(since=stamp, mine=True)["items"] == []
    assert client.get("/api/admin/reports", headers=HA, params={"since": "2020-01-01T00:00:00+08:00"}).status_code == 200
    assert client.get("/api/admin/reports", headers=HA, params={"since": "yesterday"}).status_code == 422
    # A whole hazard group is rebuilt when only one of its rows changed.
    h1 = send("hazard", where=(13.80, 121.10))
    stamp = listing()["server_time"]
    h2 = send("hazard", where=(13.8003, 121.10))
    item = listing(since=stamp)["items"][0]
    assert item["id"] == h1 and item["report_count"] == 2 and item["phones"] == 2 and h2 != h1
    for rid in (new, h1):
        assert act(HA, rid, "mark-false", reason="test report").status_code == 200


# ---------------------------------------------------------------- 2. summary

def test_summary_counts_reports_places_and_removed_centers_in_one_call():
    base = client.get("/api/admin/summary", headers=HA).json()
    assert set(base) == {"server_time", "new_reports", "being_handled", "mine", "pending_places", "removed_centers"}
    h = send("hazard", where=(13.70, 121.05))
    send("hazard", where=(13.7003, 121.05))  # same hazard: counts once
    a, b = send("help", where=(13.69, 121.06)), send("help", where=(13.68, 121.06))
    s = client.get("/api/admin/summary", headers=HA).json()
    assert s["new_reports"] == base["new_reports"] + 3  # one hazard + two help requests
    assert act(HA, a, "take").status_code == 200 and act(HB, b, "take").status_code == 200 and act(HA, h, "take").status_code == 200
    s2 = client.get("/api/admin/summary", headers=HA).json()
    assert s2["new_reports"] == s["new_reports"] - 3
    assert s2["being_handled"] == s["being_handled"] + 3
    assert s2["mine"] == s["mine"] + 2
    assert client.get("/api/admin/summary", headers=HB).json()["mine"] == s["mine"] + 1
    for rid, who in ((a, HA), (b, HB), (h, HA)):
        assert act(who, rid, "resolve", what_was_done="Helped on site").status_code == 200
    s3 = client.get("/api/admin/summary", headers=HA).json()
    assert s3["being_handled"] == s["being_handled"] and s3["new_reports"] == s2["new_reports"]

    # Places waiting for approval, and centers removed.
    body = {"name": "Console Gym", "center_type": "temporary", "max_capacity": 80, "latitude": 13.66, "longitude": 121.02}
    r = client.post("/api/evacuation-centers", headers={"X-Phone-Id": phone()}, json=body)
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    assert client.get("/api/admin/summary", headers=HA).json()["pending_places"] == base["pending_places"] + 1
    assert client.post(f"/api/admin/places/{fid}/approve", headers=HA).status_code == 200
    assert client.get("/api/admin/summary", headers=HA).json()["pending_places"] == base["pending_places"]
    assert client.delete(f"/api/evacuation-centers/{fid}", headers=HA).status_code == 200
    assert client.get("/api/admin/summary", headers=HA).json()["removed_centers"] == base["removed_centers"] + 1
    assert client.post(f"/api/evacuation-centers/{fid}/restore", headers=HA).status_code == 200
    assert client.get("/api/admin/summary", headers=HA).json()["removed_centers"] == base["removed_centers"]
    assert client.get("/api/admin/summary", headers=NO_AUTH).status_code == 401


# ---------------------------------------------------------------- 3. my activity

def test_my_activity_lists_only_my_actions_and_counts_what_i_handled_today():
    make_user("Cy Admin")
    HC = auth("Cy Admin")
    mine_a, mine_b, mine_c, theirs = send("help"), send("help"), send("help"), send("help")
    assert act(HC, mine_a, "take").status_code == 200
    assert act(HC, mine_a, "resolve", what_was_done="Helped on site").status_code == 200  # take + resolve: one report
    assert act(HC, mine_b, "take").status_code == 200
    assert act(HC, mine_b, "release").status_code == 200  # taken then given back: not handled
    assert act(HC, mine_c, "mark-false", reason="Prank or test report").status_code == 200
    assert act(HB, theirs, "take").status_code == 200
    assert act(HB, theirs, "resolve", what_was_done="Helped on site").status_code == 200
    r = client.get("/api/admin/me/activity", headers=HC)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["handled_today"] == 2
    actions = [(i["action"], i["target"]) for i in data["items"]]
    assert actions[0] == ("report.mark_false", f"report:{mine_c}")  # newest first
    assert ("report.release", f"report:{mine_b}") in actions
    assert all(t != f"report:{theirs}" for _, t in actions)  # nobody else's actions
    assert not any(a.startswith("auth.") for a, _ in actions)  # sign-ins are not actions
    assert next(i for i in data["items"] if i["action"] == "report.resolve")["detail"] == {"kind": "help", "what_was_done": "Helped on site"}
    assert len(client.get("/api/admin/me/activity", headers=HC, params={"limit": 2}).json()["items"]) == 2
    assert client.get("/api/admin/me/activity", headers=HC, params={"limit": 0}).status_code == 422
    assert client.get("/api/admin/me/activity", headers=NO_AUTH).status_code == 401
    # The new Admin with no actions sees an empty list, not somebody else's.
    make_user("Dee Admin")
    empty = client.get("/api/admin/me/activity", headers=auth("Dee Admin")).json()
    assert empty["handled_today"] == 0 and empty["items"] == []


def test_today_starts_at_local_midnight():
    now = datetime(2026, 11, 25, 17, 30)  # 01:30 on the 26th in Manila (UTC+8)
    assert console_service.today_start_utc(now) == datetime(2026, 11, 25, 16, 0)
    now = datetime(2026, 11, 25, 3, 0)  # 11:00 on the 25th in Manila
    assert console_service.today_start_utc(now) == datetime(2026, 11, 24, 16, 0)
    data = client.get("/api/admin/me/activity", headers=HA).json()
    start = datetime.fromisoformat(data["today_starts_at"].replace("Z", "+00:00"))
    assert start.tzinfo is not None and timedelta(0) <= datetime.now(timezone.utc) - start < timedelta(hours=24, minutes=1)


# ---------------------------------------------------------------- 4. contact settings

def test_contact_settings_are_null_until_set_and_the_control_room_number_is_never_public():
    pub = client.get("/api/support-contact")
    assert pub.status_code == 200 and pub.json() == {"support_email": None, "support_number": None}
    adm = client.get("/api/admin/contact-settings", headers=HA).json()
    assert adm["control_room_number"] is None and adm["support_email"] is None and adm["support_number"] is None
    r = client.patch("/api/admin/contact-settings", headers=HA, json={
        "control_room_number": "043 723 0000", "support_email": "help@silong.example", "support_number": "0917 111 2222"})
    assert r.status_code == 200, r.text
    assert r.json()["control_room_number"] == "043 723 0000" and r.json()["updated_by"] == "Ana Admin"
    pub = client.get("/api/support-contact").json()
    assert pub == {"support_email": "help@silong.example", "support_number": "0917 111 2222"}
    assert "043 723 0000" not in client.get("/api/support-contact").text
    for path in ("/api/emergency-numbers", "/api/advisories", "/api/facilities", "/api/health"):
        assert "043 723 0000" not in client.get(path).text
    # Another Admin reads the same values; partial edits keep the rest; the change is audited with the name.
    assert client.get("/api/admin/contact-settings", headers=HB).json()["control_room_number"] == "043 723 0000"
    assert client.patch("/api/admin/contact-settings", headers=HB, json={"support_email": "new@silong.example"}).status_code == 200
    got = client.get("/api/admin/contact-settings", headers=HA).json()
    assert got["support_email"] == "new@silong.example" and got["support_number"] == "0917 111 2222"
    rows = audit_rows("settings.contact_update")
    assert [r[0] for r in rows] == ["Ana Admin", "Ben Admin"]
    detail = json.loads(SessionLocalAudit("settings.contact_update")[-1].detail)
    assert detail == {"changed": ["support_email"], "was": {"support_email": "help@silong.example"}}
    # Same value again changes and logs nothing.
    assert client.patch("/api/admin/contact-settings", headers=HB, json={"support_email": "new@silong.example"}).status_code == 200
    assert len(audit_rows("settings.contact_update")) == 2
    # Clearing gives null again, never placeholder text.
    r = client.patch("/api/admin/contact-settings", headers=HA, json={"support_number": None, "control_room_number": "  "})
    assert r.status_code == 200 and r.json()["support_number"] is None and r.json()["control_room_number"] is None
    assert client.get("/api/support-contact").json() == {"support_email": "new@silong.example", "support_number": None}
    assert len(audit_rows("settings.contact_update")) == 3


def SessionLocalAudit(action):
    db = SessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.action == action).order_by(AuditLog.id).all()
    finally:
        db.close()


def test_contact_settings_are_checked_and_need_a_signed_in_admin():
    url = "/api/admin/contact-settings"
    assert client.get(url).status_code == 401 and client.patch(url, json={"support_email": "a@b.co"}).status_code == 401
    bad = [{}, {"support_email": "not an email"}, {"support_email": "a@b"}, {"support_number": "call me"},
           {"control_room_number": "12"}, {"support_email": "a" * 130 + "@b.co"}, {"something_else": "x"}]
    for body in bad:
        assert client.patch(url, headers=HA, json=body).status_code == 422, body
    assert client.post("/api/support-contact", json={}).status_code == 405  # public side is read only


# ---------------------------------------------------------------- 5. emergency number categories

def test_emergency_numbers_carry_a_category_the_sheet_can_filter_on():
    nums = client.get("/api/emergency-numbers").json()
    assert nums[0]["number"] == "911" and nums[0]["category"] is None  # untagged until an Admin tags it
    made = {}
    for cat in ("medical", "accident", "flood", "violence", "missing_person"):
        r = client.post("/api/admin/emergency-numbers", headers=HA, json={"number": "0917 5550000", "name": f"{cat} line", "category": cat})
        assert r.status_code == 201, r.text
        assert r.json()["category"] == cat
        made[cat] = r.json()["id"]
    plain = client.post("/api/admin/emergency-numbers", headers=HA, json={"number": "143", "name": "Red Cross"})
    assert plain.status_code == 201 and plain.json()["category"] is None  # the old body still works
    only = client.get("/api/emergency-numbers", params={"category": "flood"}).json()
    assert [n["id"] for n in only] == [made["flood"]]
    assert len(client.get("/api/emergency-numbers").json()) == 7  # no filter: everything
    assert client.get("/api/emergency-numbers", params={"category": "fire"}).status_code == 422
    assert client.post("/api/admin/emergency-numbers", headers=HA, json={"number": "143", "name": "X", "category": "fire"}).status_code == 422
    # Edit: set, change and clear it; audited.
    nid = plain.json()["id"]
    assert client.patch(f"/api/admin/emergency-numbers/{nid}", headers=HB, json={"category": "medical"}).json()["category"] == "medical"
    assert client.patch(f"/api/admin/emergency-numbers/{nid}", headers=HB, json={"category": None}).json()["category"] is None
    assert client.patch(f"/api/admin/emergency-numbers/{nid}", headers=HB, json={"category": "fire"}).status_code == 422
    assert client.patch(f"/api/admin/emergency-numbers/{nid}", headers=HB, json={"name": "Philippine Red Cross"}).json()["category"] is None
    assert [r[0] for r in audit_rows("emergency_number.update")] == ["Ben Admin", "Ben Admin", "Ben Admin"]


OLD_NUMBERS = """
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("CREATE TABLE emergency_numbers (id INTEGER PRIMARY KEY, number VARCHAR NOT NULL, name VARCHAR NOT NULL, description VARCHAR, position INTEGER NOT NULL DEFAULT 0)")
con.execute("INSERT INTO emergency_numbers (number, name, position) VALUES ('911', 'National Emergency', 0), ('143', 'Red Cross', 1)")
con.commit()
"""
START = """
import json
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
print(json.dumps({"numbers": c.get("/api/emergency-numbers").json(), "support": c.get("/api/support-contact").json(),
                  "health": c.get("/api/health").status_code}))
"""


def _run(code, *args, db_path):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db_path}")
    out = subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, cwd=BACKEND, env=env)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_an_older_database_gets_the_category_column_and_the_settings_table_and_keeps_its_numbers():
    old = Path(_tmp) / "old-update13.db"
    _run(OLD_NUMBERS, str(old), db_path=old)
    cols = {r[1] for r in sqlite3.connect(old).execute("PRAGMA table_info(emergency_numbers)")}
    assert "category" not in cols  # really an older database
    for _ in range(2):  # starting twice changes nothing the second time
        out = json.loads(_run(START, db_path=old).strip().splitlines()[-1])
        assert out["health"] == 200 and out["support"] == {"support_email": None, "support_number": None}
        assert [(n["number"], n["category"]) for n in out["numbers"]] == [("911", None), ("143", None)]
    con = sqlite3.connect(old)
    assert "category" in {r[1] for r in con.execute("PRAGMA table_info(emergency_numbers)")}
    assert con.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 0
    # The upgrade function alone is idempotent too.
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{old}")
    assert content_service.upgrade_number_columns(engine) == []


def run_all() -> int:
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} of {len(tests)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_all())
