"""
Part 3 checks: added places (pending / approve / reject), removal and restore by staff, the
30-day purge, who a status came from, overrides, capacity corrections, and upgrading an
older database.

Run from the backend folder (needs `pip install -r requirements-dev.txt` once):

    py tests/test_places.py

or every test file in turn (accounts, reports, places):

    py tests/run_all.py

It uses its own temporary database, so typhoon.db is never touched.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

# Must be set BEFORE the app is imported: own database, no limits in the way.
_tmp = tempfile.mkdtemp(prefix="silong-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "1000"
os.environ["STATUS_COOLDOWN_SECONDS"] = "0"
os.environ["STATUS_IP_MAX_UPDATES"] = "100000"
os.environ["MANAGE_MAX_ACTIONS"] = "100000"
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, config, evac_service, place_service  # noqa: E402
from app import main as main_mod  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    ActionLog, AuditLog, DeletedFacility, Facility, FacilityRemoval, StatusUpdate, UserEvacuationCenter,
)

client = TestClient(app)
PASSWORD = "correct horse 1"


def db_session():
    return SessionLocal()


def make_user(name, role):
    db = db_session()
    try:
        return accounts.create_user(db, name, PASSWORD, role, actor="test setup").id
    finally:
        db.close()


def auth(name):
    r = client.post("/api/auth/sign-in", json={"name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


make_user("Pia Places Responder", "responder")
make_user("Pat Places Admin", "super_admin")
H_RESP, H_ADMIN = auth("Pia Places Responder"), auth("Pat Places Admin")
NO_AUTH = {}

_phones = iter(range(1, 100_000))
_spots = iter(range(1, 10_000))


def new_phone():
    """A random-looking phone ID (16+ characters), different every call."""
    return f"phone-places-{next(_phones):08d}-abcdef"


def new_spot():
    """A place inside Batangas City, at least 1 km from every other spot handed out here."""
    n = next(_spots)
    return (13.62 + 0.0125 * (n % 18), 121.00 + 0.0125 * (n // 18 % 13))


def place_body(name, where=None, **extra):
    where = where or new_spot()
    return {"name": name, "center_type": "permanent", "max_capacity": 100,
            "latitude": where[0], "longitude": where[1], **extra}


_KEYS = {}


def key_of(fid):
    """The facility key ("user:<n>") of a place added in this test run. The n is NOT the facility id."""
    return _KEYS[fid]


def add_place(phone, name, where=None, **extra):
    headers = {"X-Phone-Id": phone} if phone else {}
    r = client.post("/api/evacuation-centers", headers=headers, json=place_body(name, where, **extra))
    if r.status_code == 201:
        _KEYS[r.json()["id"]] = r.json()["key"]
    return r


def listing(phone=None):
    headers = {"X-Phone-Id": phone} if phone else {}
    r = client.get("/api/facilities", headers=headers)
    assert r.status_code == 200, r.text
    return {f["id"]: f for f in r.json()}


def approved_place(name, where=None, capacity=100):
    """A public place: added by a fresh phone and approved by the responder. Returns its id."""
    r = add_place(new_phone(), name, where, max_capacity=capacity)
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    assert client.post(f"/api/responder/places/{fid}/approve", headers=H_RESP).status_code == 200
    return fid


def report(fid, status="open", headers=None, **extra):
    return client.post(f"/api/facilities/{fid}/status", headers=headers or {}, json={"status": status, **extra})


def audit_rows(action=None):
    db = db_session()
    try:
        q = db.query(AuditLog).order_by(AuditLog.id)
        if action:
            q = q.filter(AuditLog.action == action)
        return [(a.actor_name, a.action, a.target, json.loads(a.detail) if a.detail else None) for a in q.all()]
    finally:
        db.close()


def backdate_removal(fid, days):
    db = db_session()
    try:
        key = db.get(Facility, fid).key
        for r in db.query(FacilityRemoval).filter(FacilityRemoval.facility_key == key).all():
            r.removed_at = r.removed_at - timedelta(days=days)
        db.commit()
    finally:
        db.close()


def count_rows(fid, key):
    db = db_session()
    try:
        return {
            "facility": db.query(Facility).filter(Facility.id == fid).count(),
            "status": db.query(StatusUpdate).filter(StatusUpdate.facility_id == fid).count(),
            "removal": db.query(FacilityRemoval).filter(FacilityRemoval.facility_key == key).count(),
            "action_log": db.query(ActionLog).filter(ActionLog.facility_key == key).count(),
            "user_row": db.query(UserEvacuationCenter).filter(UserEvacuationCenter.id == int(key.split(":")[1])).count()
            if key.startswith("user:") else 0,
        }
    finally:
        db.close()


# ---------------------------------------------------------------- adding: pending

def test_added_place_starts_pending_and_only_its_sender_sees_it():
    mine, other = new_phone(), new_phone()
    r = add_place(mine, "Pending Gym One")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["approval_status"] == "pending" and body["source"] == "user" and body["status"] is None
    fid = body["id"]

    assert fid in listing(mine) and listing(mine)[fid]["approval_status"] == "pending"
    assert fid not in listing(other)  # another phone
    assert fid not in listing(None)  # no phone ID at all
    # staff do not get it in the public list either (they review it in the queue)
    assert fid not in {f["id"] for f in client.get("/api/facilities", headers=H_RESP).json()}


def test_pending_place_cannot_be_read_or_updated_by_others():
    mine, other = new_phone(), new_phone()
    fid = add_place(mine, "Pending Gym Two").json()["id"]
    # the sender can update its status and read the history ...
    assert report(fid, "open", headers={"X-Phone-Id": mine}).status_code == 201
    assert client.get(f"/api/facilities/{fid}/status/history", headers={"X-Phone-Id": mine}).status_code == 200
    # ... nobody else can, even by guessing the number
    assert report(fid, "full", headers={"X-Phone-Id": other}).status_code == 404
    assert report(fid, "full").status_code == 404
    assert client.get(f"/api/facilities/{fid}/status/history", headers={"X-Phone-Id": other}).status_code == 404
    assert client.get(f"/api/facilities/{fid}/status/history").status_code == 404


def test_adding_without_a_phone_id_still_works_but_the_sender_cannot_see_it_again():
    r = add_place(None, "Pending Gym No Phone")
    assert r.status_code == 201 and r.json()["approval_status"] == "pending"
    assert r.json()["id"] not in listing(None)
    # staff still find it in the queue
    ids = [p["id"] for p in client.get("/api/responder/places", headers=H_RESP).json()]
    assert r.json()["id"] in ids


def test_a_malformed_phone_id_is_refused_like_in_the_reports():
    r = client.post("/api/evacuation-centers", headers={"X-Phone-Id": "short"}, json=place_body("Bad Phone Gym"))
    assert r.status_code == 400


def test_possible_duplicate_is_flagged_for_the_admin_not_refused():
    spot = new_spot()
    original = approved_place("Duplicate Court", spot)
    r = add_place(new_phone(), "duplicate  court!", (spot[0] + 0.0001, spot[1]))  # ~11 m away, same name once tidied
    assert r.status_code == 201, r.text
    queue = {p["id"]: p for p in client.get("/api/responder/places", headers=H_RESP).json()}
    dup = queue[r.json()["id"]]["possible_duplicate"]
    assert dup["id"] == original and dup["approval_status"] == "approved" and dup["removed"] is False
    assert 0 < dup["distance_m"] <= config.DUPLICATE_METERS
    # the sender's own answer does not say what it looks like
    assert "possible_duplicate" not in r.json()
    # a different name or more than 30 m away is not flagged
    far = add_place(new_phone(), "Duplicate Court", (spot[0] + 0.001, spot[1])).json()["id"]  # ~110 m
    other = add_place(new_phone(), "Another Court", (spot[0], spot[1] + 0.0001)).json()["id"]
    queue = {p["id"]: p for p in client.get("/api/responder/places", headers=H_RESP).json()}
    assert queue[far]["possible_duplicate"] is None and queue[other]["possible_duplicate"] is None


def test_a_duplicate_of_a_removed_center_is_flagged_as_removed():
    spot = new_spot()
    original = approved_place("Removed Twin Hall", spot)
    assert client.delete(f"/api/evacuation-centers/{original}", headers=H_RESP).status_code == 200
    r = add_place(new_phone(), "Removed Twin Hall", spot)
    assert r.status_code == 201
    dup = {p["id"]: p for p in client.get("/api/responder/places", headers=H_RESP).json()}[r.json()["id"]]["possible_duplicate"]
    assert dup["id"] == original and dup["removed"] is True


def test_one_phone_cannot_flood_the_queue():
    phone = new_phone()
    spot = new_spot()
    assert add_place(phone, "Flood Gym", spot).status_code == 201
    again = add_place(phone, "Flood Gym", spot)  # same place again from the same phone
    assert again.status_code == 409 and "waiting for approval" in again.json()["detail"]
    for i in range(config.PENDING_PLACES_PER_PHONE - 1):
        assert add_place(phone, f"Flood Gym {i}").status_code == 201
    over = add_place(phone, "Flood Gym Over")
    assert over.status_code == 429 and "waiting for approval" in over.json()["detail"]


# ---------------------------------------------------------------- approve / reject

def test_approve_makes_it_public_and_is_audited():
    mine, other = new_phone(), new_phone()
    fid = add_place(mine, "Approve Me Gym").json()["id"]
    assert fid not in listing(other)

    r = client.post(f"/api/responder/places/{fid}/approve", headers=H_RESP)
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == "approved" and r.json()["reviewed_by"] == "Pia Places Responder"
    assert fid in listing(other) and listing(other)[fid]["approval_status"] == "approved"
    assert fid in listing(None)
    assert report(fid, "open", headers={"X-Phone-Id": other}).status_code == 201  # anybody can report on it now

    again = client.post(f"/api/responder/places/{fid}/approve", headers=H_RESP)  # a second tap
    assert again.status_code == 200 and "already" in again.json()["message"]
    approvals = [a for a in audit_rows("place.approve") if a[2].startswith(f"place:{fid} ")]
    assert len(approvals) == 1 and approvals[0][0] == "Pia Places Responder"
    assert fid not in [p["id"] for p in client.get("/api/responder/places", headers=H_RESP).json()]  # left the queue


def test_reject_hides_it_from_everyone_and_keeps_the_reason_in_the_audit_log():
    mine = new_phone()
    fid = add_place(mine, "Reject Me Gym").json()["id"]
    r = client.post(f"/api/responder/places/{fid}/reject", headers=H_ADMIN, json={"reason": "Not a real place"})
    assert r.status_code == 200 and r.json()["approval_status"] == "rejected"
    assert r.json()["reject_reason"] == "Not a real place"
    for headers in ({"X-Phone-Id": mine}, {}):  # not even its sender
        assert fid not in {f["id"]: f for f in client.get("/api/facilities", headers=headers).json()}
    assert report(fid, "open", headers={"X-Phone-Id": mine}).status_code == 404
    assert fid in [p["id"] for p in client.get("/api/responder/places?status=rejected", headers=H_RESP).json()]
    assert fid not in [p["id"] for p in client.get("/api/responder/places", headers=H_RESP).json()]
    rows = [a for a in audit_rows("place.reject") if a[2].startswith(f"place:{fid} ")]
    assert rows and rows[0][0] == "Pat Places Admin" and rows[0][3]["reason"] == "Not a real place"
    # no body at all is fine too (the reason is optional)
    other = add_place(new_phone(), "Reject Me Too").json()["id"]
    assert client.post(f"/api/responder/places/{other}/reject", headers=H_RESP).status_code == 200
    # a rejection can be undone by approving
    assert client.post(f"/api/responder/places/{fid}/approve", headers=H_RESP).json()["approval_status"] == "approved"


def test_a_place_already_on_the_map_cannot_be_rejected_only_removed():
    fid = approved_place("Already Public Gym")
    r = client.post(f"/api/responder/places/{fid}/reject", headers=H_RESP)
    assert r.status_code == 409 and "Remove" in r.json()["detail"]


# ---------------------------------------------------------------- who may do what

def test_a_user_cannot_remove_restore_approve_or_list_for_everyone():
    fid = approved_place("Users Cannot Touch Gym")
    pending = add_place(new_phone(), "Users Cannot Approve Gym").json()["id"]
    bad_token = {"Authorization": "Bearer not-a-real-token"}
    for headers in (NO_AUTH, bad_token, {"X-Phone-Id": new_phone()}):
        assert client.delete(f"/api/evacuation-centers/{fid}", headers=headers).status_code == 401
        assert client.post(f"/api/evacuation-centers/{fid}/restore", headers=headers).status_code == 401
        assert client.get("/api/evacuation-centers/removed", headers=headers).status_code == 401
        assert client.get("/api/responder/places", headers=headers).status_code == 401
        assert client.post(f"/api/responder/places/{pending}/approve", headers=headers).status_code == 401
        assert client.post(f"/api/responder/places/{pending}/reject", headers=headers).status_code == 401
        assert client.delete(f"/api/admin/places/{fid}", headers=headers).status_code == 401
        assert client.post(f"/api/responder/facilities/{fid}/status-override", headers=headers, json={"status": "full"}).status_code == 401
        assert client.post(f"/api/responder/facilities/{fid}/capacity-correction", headers=headers, json={"max_capacity": 5}).status_code == 401
        assert client.get(f"/api/responder/facilities/{fid}/status-history", headers=headers).status_code == 401
    assert fid in listing(None)  # nothing was removed
    assert pending not in listing(None)


def test_only_a_super_admin_can_delete_for_good():
    fid = approved_place("Responder Cannot Delete Gym")
    client.delete(f"/api/evacuation-centers/{fid}", headers=H_RESP)
    r = client.delete(f"/api/admin/places/{fid}", headers=H_RESP)
    assert r.status_code == 403
    assert count_rows(fid, key_of(fid))["facility"] == 1  # still there


# ---------------------------------------------------------------- remove and restore

def test_admin_removal_hides_it_for_everyone_and_restore_brings_it_back():
    fid = approved_place("Remove And Restore Gym")
    report(fid, "almost_full", people_inside=60)
    assert fid in listing(new_phone())

    r = client.delete(f"/api/evacuation-centers/{fid}", headers=H_RESP)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removed_by"] == "Pia Places Responder" and body["days_left"] == config.REMOVED_CENTERS_KEEP_DAYS
    assert body["delete_after"] > body["removed_at"] and "restored" in body["message"]
    assert fid not in listing(None) and fid not in listing(new_phone())
    assert report(fid, "open").status_code == 404  # hidden means hidden

    again = client.delete(f"/api/evacuation-centers/{fid}", headers=H_RESP)  # a second tap
    assert again.status_code == 200 and "already" in again.json()["message"]

    removed = client.get("/api/evacuation-centers/removed", headers=H_RESP).json()
    assert fid in [x["id"] for x in removed]

    back = client.post(f"/api/evacuation-centers/{fid}/restore", headers=H_ADMIN)
    assert back.status_code == 200 and back.json()["id"] == fid
    assert fid in listing(None)
    assert listing(None)[fid]["status"]["status"] == "almost_full"  # its history came back with it
    assert fid not in [x["id"] for x in client.get("/api/evacuation-centers/removed", headers=H_RESP).json()]
    assert client.post(f"/api/evacuation-centers/{fid}/restore", headers=H_ADMIN).status_code == 200  # not removed: nothing to do

    mine = [a for a in audit_rows() if a[2] and a[2].startswith(f"place:{fid} ") and a[1] in ("place.remove", "place.restore")]
    assert [(a[0], a[1]) for a in mine] == [("Pia Places Responder", "place.remove"), ("Pat Places Admin", "place.restore")]


def test_hospitals_and_unapproved_places_cannot_be_removed():
    hospital = next(f for f in listing(None).values() if f["type"] == "hospital")
    assert client.delete(f"/api/evacuation-centers/{hospital['id']}", headers=H_RESP).status_code == 422
    pending = add_place(new_phone(), "Pending Not Removable").json()["id"]
    r = client.delete(f"/api/evacuation-centers/{pending}", headers=H_RESP)
    assert r.status_code == 409 and "Reject" in r.json()["detail"]
    assert client.delete("/api/evacuation-centers/99999999", headers=H_RESP).status_code == 404


# ---------------------------------------------------------------- the 30-day purge

def test_setting_for_how_long_removed_centers_are_kept_is_30_days_and_has_an_env_override():
    assert config.REMOVED_CENTERS_KEEP_DAYS == 30
    out = subprocess.run(
        [sys.executable, "-c", "from app import config; print(config.REMOVED_CENTERS_KEEP_DAYS)"],
        capture_output=True, text=True, cwd=BACKEND, env=dict(os.environ, REMOVED_CENTERS_KEEP_DAYS="7"),
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "7"


def test_purge_deletes_a_center_removed_over_30_days_ago_with_its_history():
    fid = approved_place("Purge Me Gym")
    key = key_of(fid)
    report(fid, "open", people_inside=10)
    report(fid, "full", people_inside=100)
    client.delete(f"/api/evacuation-centers/{fid}", headers=H_RESP)
    before = count_rows(fid, key)
    assert before["status"] == 2 and before["removal"] == 1 and before["action_log"] == 1 and before["user_row"] == 1

    db = db_session()
    try:
        now = evac_service._now()
        assert place_service.purge_removed_centers(db, now=now + timedelta(days=29)) == 0  # day 29: still kept
        assert count_rows(fid, key)["facility"] == 1
        assert place_service.purge_removed_centers(db, now=now + timedelta(days=31)) >= 1  # day 31: deleted
    finally:
        db.close()
    assert count_rows(fid, key) == {"facility": 0, "status": 0, "removal": 0, "action_log": 0, "user_row": 0}
    assert fid not in [x["id"] for x in client.get("/api/evacuation-centers/removed", headers=H_RESP).json()]
    purge = [a for a in audit_rows("place.purge") if any(p["key"] == key for p in a[3]["places"])]
    assert len(purge) == 1 and purge[0][0] == "(system)" and purge[0][3]["older_than_days"] == 30


def test_purge_keeps_restored_centers_and_pending_places_and_deletes_old_rejected_ones():
    restored = approved_place("Restored Stays Gym")
    client.delete(f"/api/evacuation-centers/{restored}", headers=H_RESP)
    client.post(f"/api/evacuation-centers/{restored}/restore", headers=H_RESP)
    pending = add_place(new_phone(), "Pending Stays Gym").json()["id"]
    rejected = add_place(new_phone(), "Rejected Goes Gym").json()["id"]
    client.post(f"/api/responder/places/{rejected}/reject", headers=H_RESP)

    db = db_session()
    try:
        place_service.purge_removed_centers(db, now=evac_service._now() + timedelta(days=31))
    finally:
        db.close()
    assert count_rows(restored, key_of(restored))["facility"] == 1
    assert count_rows(pending, key_of(pending))["facility"] == 1
    assert count_rows(rejected, key_of(rejected)) == {"facility": 0, "status": 0, "removal": 0, "action_log": 0, "user_row": 0}
    assert restored in listing(None)


def test_a_center_from_a_data_file_stays_deleted_after_the_purge_and_a_restart():
    osm = dict(name="Data File Test Gym", type="evacuation_center", latitude=13.80, longitude=121.10,
               address="Test Road", contact=None, notes="Source: OpenStreetMap way/999001")
    original = main_mod.load_facilities
    main_mod.load_facilities = lambda: original() + [osm]
    try:
        main_mod.sync_facilities()
        fid = next(f["id"] for f in listing(None).values() if f["key"] == "osm:way/999001")
        client.delete(f"/api/evacuation-centers/{fid}", headers=H_RESP)
        db = db_session()
        try:
            place_service.purge_removed_centers(db, now=evac_service._now() + timedelta(days=31))
            assert db.get(DeletedFacility, "osm:way/999001") is not None
        finally:
            db.close()
        main_mod.sync_facilities()  # what the next start does: read the data file again
        assert "osm:way/999001" not in {f["key"] for f in listing(None).values()}
        db = db_session()
        try:
            assert db.query(Facility).filter(Facility.key == "osm:way/999001").count() == 0
        finally:
            db.close()
    finally:
        main_mod.load_facilities = original


def test_a_super_admin_can_delete_a_removed_center_sooner_and_only_that():
    fid = approved_place("Delete Sooner Gym")
    key = key_of(fid)
    report(fid, "open")
    # not removed yet: refused
    r = client.delete(f"/api/admin/places/{fid}", headers=H_ADMIN)
    assert r.status_code == 409 and "Remove it first" in r.json()["detail"]
    client.delete(f"/api/evacuation-centers/{fid}", headers=H_RESP)
    assert client.delete(f"/api/admin/places/{fid}", headers=H_RESP).status_code == 403  # a responder cannot
    assert count_rows(fid, key)["facility"] == 1
    assert client.delete(f"/api/admin/places/{fid}", headers=H_ADMIN).status_code == 200
    assert count_rows(fid, key) == {"facility": 0, "status": 0, "removal": 0, "action_log": 0, "user_row": 0}
    rows = [a for a in audit_rows("place.delete") if a[2].startswith(f"place:{fid} ")]
    assert rows and rows[0][0] == "Pat Places Admin"
    # a rejected place can be deleted sooner too
    rejected = add_place(new_phone(), "Delete Rejected Sooner").json()["id"]
    client.post(f"/api/responder/places/{rejected}/reject", headers=H_RESP)
    assert client.delete(f"/api/admin/places/{rejected}", headers=H_ADMIN).status_code == 200
    # a pending place is neither
    pending = add_place(new_phone(), "Delete Pending Refused").json()["id"]
    assert client.delete(f"/api/admin/places/{pending}", headers=H_ADMIN).status_code == 409


def _run_python(code, db_path):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db_path}")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=BACKEND, env=env)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_the_purge_runs_from_the_script_and_on_startup():
    db_path = Path(_tmp) / "test.db"
    # one for the script ...
    a = approved_place("Script Purge Gym")
    client.delete(f"/api/evacuation-centers/{a}", headers=H_RESP)
    backdate_removal(a, 31)
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db_path}")
    out = subprocess.run([sys.executable, "scripts/purge_removed_centers.py"], capture_output=True, text=True, cwd=BACKEND, env=env)
    assert out.returncode == 0, out.stderr
    assert "Deleted 1 removed or rejected place(s) older than 30 days." in out.stdout, out.stdout
    assert count_rows(a, key_of(a))["facility"] == 0
    # ... and one for the start of the server
    b = approved_place("Startup Purge Gym")
    client.delete(f"/api/evacuation-centers/{b}", headers=H_RESP)
    backdate_removal(b, 31)
    out = _run_python("from app.main import app", db_path)
    assert "Deleted 1 removed or rejected place(s)" in out, out
    assert count_rows(b, key_of(b))["facility"] == 0


# ---------------------------------------------------------------- where a status came from

def test_status_from_a_user_and_from_an_official_are_told_apart():
    fid = approved_place("Source Gym")
    assert listing(None)[fid]["status"] is None

    r = report(fid, "open", people_inside=20)
    assert r.status_code == 201
    assert r.json()["source"] == "user" and r.json()["source_label"] == "Reported by a user"
    s = listing(None)[fid]["status"]
    assert s["source"] == "user" and s["source_label"] == "Reported by a user"

    for headers, who in ((H_RESP, "Pia Places Responder"), (H_ADMIN, "Pat Places Admin")):
        r = report(fid, "almost_full", headers=headers, people_inside=80)
        assert r.status_code == 201, r.text
        assert r.json()["source"] == "official" and r.json()["source_label"] == "Confirmed by official"
        s = listing(None)[fid]["status"]
        assert s["source"] == "official" and s["source_label"] == "Confirmed by official" and s["status"] == "almost_full"
        assert "changed_by" not in s  # the public list never carries a staff name
        db = db_session()
        try:
            assert db.query(StatusUpdate).filter(StatusUpdate.facility_id == fid).order_by(StatusUpdate.id.desc()).first().changed_by == who
        finally:
            db.close()
    assert report(fid, "full").json()["source"] == "user"  # a user after the official: user again
    assert [a[0] for a in audit_rows("status.update") if a[2].startswith(f"facility:{fid} ")] == ["Pia Places Responder", "Pat Places Admin"]
    # hospitals and clinics too
    clinic = next(f for f in listing(None).values() if f["type"] == "clinic")
    r = report(clinic["id"], "busy", headers=H_RESP)
    assert r.status_code == 201 and r.json()["source_label"] == "Confirmed by official"


def test_a_wrong_or_expired_token_counts_as_a_user_not_an_error():
    fid = approved_place("Bad Token Gym")
    r = report(fid, "open", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 201 and r.json()["source"] == "user"


def test_staff_are_not_held_back_by_the_per_place_cooldown_but_users_are():
    fid = approved_place("Cooldown Gym")
    old = config.STATUS_COOLDOWN_SECONDS
    config.STATUS_COOLDOWN_SECONDS = 60
    try:
        assert report(fid, "open").status_code == 201
        assert report(fid, "full").status_code == 429
        assert report(fid, "open", headers=H_RESP).status_code == 201
        assert report(fid, "full", headers=H_RESP).status_code == 201
    finally:
        config.STATUS_COOLDOWN_SECONDS = old


def test_users_can_only_send_status_data_never_name_address_or_phone():
    fid = approved_place("Only Status Gym")
    for extra in ({"name": "Hacked"}, {"address": "Somewhere"}, {"contact": "0917 000 0000"}, {"latitude": 1.0}, {"source": "official"}, {"kind": "override"}):
        assert report(fid, "open", **extra).status_code == 422, extra
    assert report(fid, "open", headers=H_RESP, source="official").status_code == 422  # not even staff
    f = listing(None)[fid]
    assert f["name"] == "Only Status Gym"


# ---------------------------------------------------------------- overrides and capacity

def test_override_is_added_to_the_history_nothing_is_erased_and_the_name_is_recorded():
    fid = approved_place("Override Gym")
    report(fid, "open", people_inside=10)
    r = client.post(f"/api/responder/facilities/{fid}/status-override", headers=H_RESP,
                    json={"status": "full", "people_inside": 100, "note": "Counted at the gate", "reason": "A user said open by mistake"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "full" and r.json()["source"] == "official" and r.json()["source_label"] == "Confirmed by official"
    s = listing(None)[fid]["status"]
    assert s["status"] == "full" and s["source"] == "official" and s["note"] == "Counted at the gate"
    assert listing(None)[fid]["people_inside"] == 100

    history = client.get(f"/api/responder/facilities/{fid}/status-history", headers=H_RESP).json()
    assert [(h["kind"], h["status"], h["source"], h["changed_by"]) for h in history] == [
        ("override", "full", "official", "Pia Places Responder"),
        ("report", "open", "user", None),
    ]
    public = client.get(f"/api/facilities/{fid}/status/history").json()
    assert [h["status"] for h in public] == ["full", "open"]  # the replaced status is still there
    rows = [a for a in audit_rows("status.override") if a[2].startswith(f"facility:{fid} ")]
    assert len(rows) == 1 and rows[0][0] == "Pia Places Responder"
    assert rows[0][3]["from_status"] == "open" and rows[0][3]["to_status"] == "full" and rows[0][3]["reason"] == "A user said open by mistake"

    # a user can still report after an override: it is the newest, nothing is locked
    assert report(fid, "almost_full", people_inside=90).status_code == 201
    assert listing(None)[fid]["status"]["source"] == "user"


def test_override_follows_the_same_rules_as_a_report():
    fid = approved_place("Override Rules Gym", capacity=50)
    ov = lambda body: client.post(f"/api/responder/facilities/{fid}/status-override", headers=H_RESP, json=body)  # noqa: E731
    assert ov({"status": "busy"}).status_code == 422  # not a status of an evacuation center
    assert ov({"status": "open", "people_inside": 500}).status_code == 422  # typo guard
    assert ov({"status": "open", "name": "Hacked"}).status_code == 422
    r = ov({"status": "open", "people_inside": 50})  # at capacity: saved as full, and it says so
    assert r.status_code == 201 and r.json()["status"] == "full" and "full" in r.json()["message"]
    clinic = next(f for f in listing(None).values() if f["type"] == "clinic")
    assert client.post(f"/api/responder/facilities/{clinic['id']}/status-override", headers=H_ADMIN, json={"status": "closed"}).status_code == 201
    pending = add_place(new_phone(), "Override Pending Gym").json()["id"]
    assert client.post(f"/api/responder/facilities/{pending}/status-override", headers=H_RESP, json={"status": "open"}).status_code == 404


def test_capacity_correction_is_a_history_row_that_does_not_make_an_old_status_look_fresh():
    fid = approved_place("Capacity Gym", capacity=100)
    first = report(fid, "open", people_inside=20).json()
    r = client.post(f"/api/responder/facilities/{fid}/capacity-correction", headers=H_RESP,
                    json={"max_capacity": 150, "reason": "Gym was measured again"})
    assert r.status_code == 200, r.text
    f = listing(None)[fid]
    assert f["max_capacity"] == 150 and f["spaces_left"] == 130
    assert f["status"]["id"] == first["id"] and f["status"]["source"] == "user"  # still the same status, same time
    assert f["status"]["updated_at"] == first["updated_at"]

    history = client.get(f"/api/responder/facilities/{fid}/status-history", headers=H_RESP).json()
    assert (history[0]["kind"], history[0]["max_capacity"], history[0]["changed_by"], history[0]["source"]) == ("capacity", 150, "Pia Places Responder", "official")
    assert len(history) == 2 and history[1]["id"] == first["id"]  # nothing erased
    assert [h["id"] for h in client.get(f"/api/facilities/{fid}/status/history").json()] == [first["id"]]  # not a status for the public
    db = db_session()
    try:
        assert db.get(UserEvacuationCenter, int(key_of(fid).split(":")[1])).max_capacity == 100  # what was typed when added is kept
    finally:
        db.close()
    rows = [a for a in audit_rows("capacity.correct") if a[2].startswith(f"facility:{fid} ")]
    assert len(rows) == 1 and rows[0][3] == {"from": 100, "to": 150, "reason": "Gym was measured again"} and rows[0][0] == "Pia Places Responder"

    # asking for the same number again changes nothing
    client.post(f"/api/responder/facilities/{fid}/capacity-correction", headers=H_RESP, json={"max_capacity": 150})
    assert len(client.get(f"/api/responder/facilities/{fid}/status-history", headers=H_RESP).json()) == 2


def test_a_user_report_cannot_undo_an_official_capacity_but_an_official_can_change_it():
    fid = approved_place("Capacity Lock Gym", capacity=100)
    # before any official number, users can change the capacity as before
    assert report(fid, "open", people_inside=10, max_capacity=120).json()["max_capacity"] == 120
    report(fid, "open", people_inside=10)
    client.post(f"/api/responder/facilities/{fid}/capacity-correction", headers=H_ADMIN, json={"max_capacity": 150})

    r = report(fid, "open", people_inside=30, max_capacity=80)  # the form always sends the number it started with
    assert r.status_code == 201 and r.json()["max_capacity"] == 150 and "set by an official" in r.json()["message"]
    assert listing(None)[fid]["max_capacity"] == 150
    r = report(fid, "open", people_inside=40, max_capacity=150)  # the same number: nothing to say
    assert r.json()["max_capacity"] == 150 and r.json()["message"] is None
    assert report(fid, "open", people_inside=40).json()["max_capacity"] == 150  # left out: carried over
    assert listing(None)[fid]["max_capacity"] == 150

    assert client.post(f"/api/responder/facilities/{fid}/capacity-correction", headers=H_RESP, json={"max_capacity": 200}).status_code == 200
    assert listing(None)[fid]["max_capacity"] == 200
    # an official report with its own number sets it too
    assert report(fid, "open", headers=H_RESP, people_inside=5, max_capacity=180).json()["max_capacity"] == 180
    assert report(fid, "open", max_capacity=10).json()["max_capacity"] == 180


def test_capacity_correction_refuses_what_makes_no_sense():
    fid = approved_place("Capacity Refuse Gym", capacity=100)
    fix = lambda fid_, body: client.post(f"/api/responder/facilities/{fid_}/capacity-correction", headers=H_RESP, json=body)  # noqa: E731
    r = fix(fid, {"max_capacity": 150})  # no status yet to sit on
    assert r.status_code == 422 and "no status yet" in r.json()["detail"]
    report(fid, "open", people_inside=90)
    assert fix(fid, {"max_capacity": 0}).status_code == 422
    assert fix(fid, {"max_capacity": 10_000_000}).status_code == 422
    assert fix(fid, {"max_capacity": 20}).status_code == 422  # 90 people inside is far more than 20
    assert fix(fid, {"max_capacity": 150, "name": "Hacked"}).status_code == 422
    hospital = next(f for f in listing(None).values() if f["type"] == "hospital")
    assert fix(hospital["id"], {"max_capacity": 10}).status_code == 422
    assert fix(99999999, {"max_capacity": 10}).status_code == 404


# ---------------------------------------------------------------- compatibility and old databases

def test_facilities_output_only_gained_fields():
    f = next(iter(listing(None).values()))
    old_fields = {"id", "key", "name", "type", "latitude", "longitude", "address", "contact", "notes", "source", "center_type",
                  "status", "people_inside", "max_capacity", "spaces_left", "percent_full", "is_outdated"}
    assert old_fields <= set(f)
    assert set(f) - old_fields == {"approval_status"}
    fid = approved_place("Output Gym")
    report(fid, "open", people_inside=5)
    s = listing(None)[fid]["status"]
    old_status = {"id", "status", "people_inside", "max_capacity", "resources", "note", "updated_at", "is_outdated", "message"}
    assert old_status <= set(s) and set(s) - old_status == {"source", "source_label"}
    assert listing(None)[fid]["center_type"] == "permanent"


OLD_SCHEMA = """
    CREATE TABLE facilities (
        id INTEGER PRIMARY KEY, key VARCHAR NOT NULL UNIQUE, name VARCHAR NOT NULL, type VARCHAR NOT NULL,
        latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, address VARCHAR, contact VARCHAR, notes TEXT);
    CREATE TABLE user_evacuation_centers (
        id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, center_type VARCHAR NOT NULL, barangay VARCHAR, address VARCHAR,
        contact VARCHAR, max_capacity INTEGER NOT NULL, latitude FLOAT NOT NULL, longitude FLOAT NOT NULL,
        note VARCHAR(140), created_at DATETIME NOT NULL);
    CREATE TABLE facility_removals (
        id INTEGER PRIMARY KEY, facility_key VARCHAR NOT NULL, removed_at DATETIME NOT NULL, restored_at DATETIME);
    CREATE TABLE status_updates (
        id INTEGER PRIMARY KEY, facility_id INTEGER NOT NULL, status VARCHAR NOT NULL, people_inside INTEGER,
        max_capacity INTEGER, resources TEXT, note VARCHAR(140), created_at DATETIME NOT NULL);
    CREATE TABLE action_log (
        id INTEGER PRIMARY KEY, action VARCHAR NOT NULL, facility_key VARCHAR NOT NULL, created_at DATETIME NOT NULL,
        ip_hash VARCHAR NOT NULL);
    INSERT INTO facilities (id, key, name, type, latitude, longitude, address) VALUES
        (1, 'user:1', 'Old Public Gym', 'evacuation_center', 13.7600, 121.0600, 'Old Road, Batangas City'),
        (2, 'user:2', 'Old Removed Court', 'evacuation_center', 13.7700, 121.0700, 'Old Lane, Batangas City');
    INSERT INTO user_evacuation_centers (id, name, center_type, max_capacity, latitude, longitude, created_at) VALUES
        (1, 'Old Public Gym', 'permanent', 200, 13.7600, 121.0600, datetime('now')),
        (2, 'Old Removed Court', 'temporary', 80, 13.7700, 121.0700, datetime('now'));
    INSERT INTO facility_removals (facility_key, removed_at) VALUES ('user:2', datetime('now', '-3 days'));
    INSERT INTO status_updates (facility_id, status, people_inside, max_capacity, created_at)
        VALUES (1, 'almost_full', 150, 200, datetime('now'));
    INSERT INTO action_log (action, facility_key, created_at, ip_hash) VALUES ('add', 'user:1', datetime('now'), 'x');
"""


def test_an_older_database_upgrades_by_itself_and_keeps_everything():
    old_db = Path(_tmp) / "old-part2b.db"
    con = sqlite3.connect(old_db)
    con.executescript(OLD_SCHEMA)
    con.commit()
    con.close()
    code = (
        "import json\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "from app import database, place_service\n"
        "c = TestClient(app)\n"
        "fs = {f['id']: f for f in c.get('/api/facilities').json()}\n"
        "print(json.dumps({\n"
        "  'ids': sorted(i for i in fs if i in (1, 2)),\n"
        "  'gym': {k: fs[1][k] for k in ('name', 'approval_status', 'max_capacity', 'center_type', 'source')},\n"
        "  'status': {k: fs[1]['status'][k] for k in ('status', 'source', 'source_label')},\n"
        "  'again': place_service.upgrade_place_columns(database.engine),\n"
        "  'removed': [(r.id, r.removed_by, r.days_left) for r in place_service.list_removed(database.SessionLocal())],\n"
        "}))\n"
    )
    out = json.loads(_run_python(code, old_db).strip().splitlines()[-1])
    assert out["ids"] == [1]  # the old public center is still public, the old removed one still hidden
    assert out["gym"] == {"name": "Old Public Gym", "approval_status": "approved", "max_capacity": 200, "center_type": "permanent", "source": "user"}
    assert out["status"] == {"status": "almost_full", "source": "user", "source_label": "Reported by a user"}
    assert out["again"] == {}  # a second start adds nothing
    assert out["removed"] == [[2, None, 27]], out["removed"]  # removed 3 days ago: 27 days left, nobody's name
    cols = lambda table: {row[1] for row in sqlite3.connect(old_db).execute(f"PRAGMA table_info({table})")}  # noqa: E731
    assert {"approval_status", "phone_hash", "reviewed_by", "reviewed_at", "reject_reason"} <= cols("user_evacuation_centers")
    assert "removed_by" in cols("facility_removals")
    assert {"source", "kind", "changed_by"} <= cols("status_updates")
    con = sqlite3.connect(old_db)
    assert con.execute("SELECT COUNT(*) FROM status_updates").fetchone()[0] == 1  # no row lost
    assert con.execute("SELECT kind FROM status_updates").fetchone()[0] == "report"
    con.close()


def test_existing_endpoints_still_work():
    assert client.get("/api/health").status_code == 200
    assert len(client.get("/api/facilities").json()) > 0


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
