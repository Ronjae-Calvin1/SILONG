"""
Part 5 checks: the .env loader, password change and reset, phone block management, place edits,
audit-log filters, the scheduled cleanup, the demo data script and the API document.

Run from the backend folder (needs `pip install -r requirements-dev.txt` once):

    py tests/test_ops.py

or every test file in turn:

    py tests/run_all.py

It uses its own temporary database, so typhoon.db is never touched.
"""
import asyncio
import importlib.util
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

# Must be set BEFORE the app is imported: own database, no limits in the way, no background task.
_tmp = tempfile.mkdtemp(prefix="silong-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "100000"
os.environ["MANAGE_MAX_ACTIONS"] = "100000"
os.environ["REPORT_PHONE_COOLDOWN_SECONDS"] = "0"
os.environ["REPORT_PHONE_MAX"] = "100000"
os.environ["REPORT_IP_MAX"] = "100000"
os.environ["PURGE_INTERVAL_MINUTES"] = "0"  # the scheduled cleanup is OFF in the tests
BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, config, maintenance, report_service  # noqa: E402
from app import main as main_mod  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog, AuthSession, BlockedPhone, Facility, Report, User,
)
from app.rate_limit import password_change_limiter, signin_limiter  # noqa: E402

client = TestClient(app)
PASSWORD = "correct horse 1"
NEW_PASSWORD = "brand new horse 2"


def db_session():
    return SessionLocal()


def make_user(name, password=PASSWORD):
    db = db_session()
    try:
        return accounts.create_user(db, name, password, actor="test setup").id
    finally:
        db.close()


def sign_in(name, password=PASSWORD):
    return client.post("/api/auth/sign-in", json={"name": name, "password": password})


def auth(name, password=PASSWORD):
    r = sign_in(name, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def phone_headers(n):
    return {"X-Phone-Id": f"opsphone-{n:04d}-abcdefghij"}


ADMIN_ID = make_user("Opsy Admin")
ADMIN_B_ID = make_user("Opsy Second Admin")


def admin():
    return auth("Opsy Admin")


def second_admin():
    return auth("Opsy Second Admin")


def audit_rows(action=None):
    db = db_session()
    try:
        q = db.query(AuditLog)
        if action:
            q = q.filter(AuditLog.action == action)
        return q.order_by(AuditLog.id).all()
    finally:
        db.close()


# ------------------------------------------------------------------ 1. .env

def test_env_file_is_loaded_and_a_real_variable_wins():
    d = Path(tempfile.mkdtemp())
    (d / ".env").write_text(
        "# a comment\n\nOPS_A=plain\nOPS_B = \"double quoted\"\nOPS_C='single quoted'\nexport OPS_D=exported\n"
        "OPS_E=keep=equals\nOPS_REAL=from the file\nnot a pair\n", encoding="utf-8")
    env = {"OPS_REAL": "from the real environment"}
    n = config.load_env_file(d / ".env", env)
    assert env == {
        "OPS_A": "plain", "OPS_B": "double quoted", "OPS_C": "single quoted", "OPS_D": "exported",
        "OPS_E": "keep=equals", "OPS_REAL": "from the real environment",
    }, env
    assert n == 5, n
    assert config.load_env_file(d / "missing.env", {}) == 0  # a missing file is fine


def test_config_reads_backend_env_end_to_end():
    """A copy of the app package next to its own .env: the file reaches config, the real environment still wins."""
    d = Path(tempfile.mkdtemp())
    shutil.copytree(BACKEND / "app", d / "app", ignore=shutil.ignore_patterns("__pycache__"))
    (d / ".env").write_text("CHAT_MAX_QUESTION_LENGTH=77\nBLOCK_EXPIRES_DAYS='5'\n", encoding="utf-8")
    code = "from app import config; print(config.CHAT_MAX_QUESTION_LENGTH, config.BLOCK_EXPIRES_DAYS)"
    base = {k: v for k, v in os.environ.items() if k not in ("CHAT_MAX_QUESTION_LENGTH", "BLOCK_EXPIRES_DAYS")}
    out = subprocess.run([sys.executable, "-c", code], cwd=d, env=base, capture_output=True, text=True)
    assert out.stdout.split() == ["77", "5"], (out.stdout, out.stderr)
    out = subprocess.run([sys.executable, "-c", code], cwd=d, env={**base, "CHAT_MAX_QUESTION_LENGTH": "11"}, capture_output=True, text=True)
    assert out.stdout.split() == ["11", "5"], (out.stdout, out.stderr)
    assert config.ENV_FILE == BACKEND / ".env"


def test_backend_env_is_ignored_by_git():
    if shutil.which("git") is None or not (REPO / ".git").exists():
        return
    r = subprocess.run(["git", "check-ignore", "-q", "backend/.env"], cwd=REPO)
    assert r.returncode == 0, "backend/.env is not ignored by git"


# ------------------------------------------------------------------ 2. passwords

def test_change_password_wrong_current_is_refused_and_limited():
    make_user("Opsy Wrong")
    password_change_limiter.reset()
    h = auth("Opsy Wrong")
    old = config.PASSWORD_CHANGE_MAX_WRONG
    config.PASSWORD_CHANGE_MAX_WRONG = 3
    try:
        for _ in range(3):
            r = client.post("/api/auth/change-password", headers=h, json={"current_password": "nope nope 1", "new_password": NEW_PASSWORD})
            assert r.status_code == 403 and r.json()["detail"] == "The current password is wrong.", r.text
        # The limit is used up: even the RIGHT password is held back now.
        r = client.post("/api/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        assert r.status_code == 429 and "Retry-After" in r.headers and "Too many" in r.json()["detail"], r.text
    finally:
        config.PASSWORD_CHANGE_MAX_WRONG = old
        password_change_limiter.reset()
    assert sign_in("Opsy Wrong", PASSWORD).status_code == 200  # the password did not change


def test_change_password_per_ip_limit_covers_many_people():
    for n in (1, 2):
        make_user(f"Opsy Ipguess {n}")
    password_change_limiter.reset()
    old = config.PASSWORD_CHANGE_IP_MAX_WRONG
    config.PASSWORD_CHANGE_IP_MAX_WRONG = 2
    try:
        h1, h2 = auth("Opsy Ipguess 1"), auth("Opsy Ipguess 2")
        body = {"current_password": "nope nope 1", "new_password": NEW_PASSWORD}
        assert client.post("/api/auth/change-password", headers=h1, json=body).status_code == 403
        assert client.post("/api/auth/change-password", headers=h2, json=body).status_code == 403
        assert client.post("/api/auth/change-password", headers=h1, json=body).status_code == 429
    finally:
        config.PASSWORD_CHANGE_IP_MAX_WRONG = old
        password_change_limiter.reset()


def test_change_password_success_ends_only_the_other_sessions():
    make_user("Opsy Changer")
    password_change_limiter.reset()
    h_here, h_other = auth("Opsy Changer"), auth("Opsy Changer")
    r = client.post("/api/auth/change-password", headers=h_here, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 200 and "changed" in r.json()["message"], r.text
    assert NEW_PASSWORD not in r.text and PASSWORD not in r.text
    assert client.get("/api/me", headers=h_here).status_code == 200  # this one stays
    assert client.get("/api/me", headers=h_other).status_code == 401  # the other one ended
    assert sign_in("Opsy Changer", PASSWORD).status_code == 401
    assert sign_in("Opsy Changer", NEW_PASSWORD).status_code == 200
    entry = [a for a in audit_rows("auth.change_password") if a.actor_name == "Opsy Changer"][-1]
    assert json.loads(entry.detail) == {"other_sessions_ended": 1}
    assert PASSWORD not in (entry.detail or "") and NEW_PASSWORD not in (entry.detail or "")


def test_change_password_rules():
    make_user("Opsy Rules")
    h = auth("Opsy Rules")
    short = client.post("/api/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422 and str(config.MIN_PASSWORD_LENGTH) in short.json()["detail"], short.text
    same = client.post("/api/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 422 and "different" in same.json()["detail"]
    assert client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 401
    assert sign_in("Opsy Rules", PASSWORD).status_code == 200  # nothing changed


def test_reset_password_is_open_to_every_admin_but_not_to_the_public():
    make_user("Opsy Target A")
    tid = make_user("Opsy Target B")
    assert client.post(f"/api/admin/users/{tid}/reset-password", json={"new_password": NEW_PASSWORD}).status_code == 401
    assert sign_in("Opsy Target B", PASSWORD).status_code == 200  # untouched
    r = client.post(f"/api/admin/users/{tid}/reset-password", headers=second_admin(), json={"new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text  # a plain Admin may reset
    assert sign_in("Opsy Target B", PASSWORD).status_code == 401 and sign_in("Opsy Target B", NEW_PASSWORD).status_code == 200
    entry = client.get("/api/admin/audit-log?action=user.reset_password", headers=admin()).json()[0]
    assert entry["actor_name"] == "Opsy Second Admin" and entry["actor_role"] == "admin"


def test_reset_password_ends_sessions_and_clears_the_lock():
    tid = make_user("Opsy Forgetful")
    h1, h2 = auth("Opsy Forgetful"), auth("Opsy Forgetful")
    for _ in range(config.SIGNIN_MAX_WRONG_TRIES):  # lock it through the real sign-in path
        sign_in("Opsy Forgetful", "wrong wrong 1")
    signin_limiter.reset()
    assert sign_in("Opsy Forgetful", PASSWORD).status_code == 423
    r = client.post(f"/api/admin/users/{tid}/reset-password", headers=admin(), json={"new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text
    assert NEW_PASSWORD not in r.text and r.json()["status"] == "active"
    assert client.get("/api/me", headers=h1).status_code == 401 and client.get("/api/me", headers=h2).status_code == 401
    assert sign_in("Opsy Forgetful", PASSWORD).status_code == 401
    assert sign_in("Opsy Forgetful", NEW_PASSWORD).status_code == 200  # the lock is gone
    db = db_session()
    try:
        u = db.get(User, tid)
        assert u.failed_attempts == 0 and u.locked_until is None
    finally:
        db.close()
    entry = audit_rows("user.reset_password")[-1]
    assert entry.actor_name == "Opsy Admin" and "Opsy Forgetful" in entry.target
    assert NEW_PASSWORD not in (entry.detail or "")


def test_reset_password_rules():
    tid = make_user("Opsy Locked By Admin")
    h = admin()
    assert client.post(f"/api/admin/users/{tid}/lock", headers=h).status_code == 200
    r = client.post(f"/api/admin/users/{tid}/reset-password", headers=h, json={"new_password": "short"})
    assert r.status_code == 422
    assert client.post("/api/admin/users/99999/reset-password", headers=h, json={"new_password": NEW_PASSWORD}).status_code == 404
    assert client.post(f"/api/admin/users/{ADMIN_ID}/reset-password", headers=h, json={"new_password": NEW_PASSWORD}).status_code == 409
    # A lock an Admin set is a separate decision: a reset leaves it, unlock undoes it.
    assert client.post(f"/api/admin/users/{tid}/reset-password", headers=h, json={"new_password": NEW_PASSWORD}).status_code == 200
    assert sign_in("Opsy Locked By Admin", NEW_PASSWORD).status_code == 423
    client.post(f"/api/admin/users/{tid}/unlock", headers=h)
    assert sign_in("Opsy Locked By Admin", NEW_PASSWORD).status_code == 200


# ------------------------------------------------------------------ 3. phone blocks

_hazard_spot = [13.70]


def send_hazard(phone_n, note="ops"):
    _hazard_spot[0] += 0.005  # far enough apart (> 100 m) that every report is its own hazard
    return client.post("/api/reports", headers=phone_headers(phone_n), json={
        "kind": "hazard", "category": "Flooded road", "latitude": _hazard_spot[0], "longitude": 121.05, "note": note})


def mark_false_via_api(report_id, h):
    r = client.post(f"/api/admin/reports/{report_id}/mark-false", headers=h, json={"reason": "Not real"})
    assert r.status_code == 200, r.text


def block_phone(phone_n):
    h = second_admin()
    for _ in range(config.FALSE_REPORTS_BEFORE_BLOCK):
        r = send_hazard(phone_n)
        assert r.status_code == 201, r.text
        mark_false_via_api(r.json()["id"], h)
    assert send_hazard(phone_n).status_code == 403


def test_blocked_phones_are_listed_without_any_phone_id():
    block_phone(101)
    r = client.get("/api/admin/blocked-phones", headers=admin())
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    assert set(rows[0]) == {"id", "blocked_at", "false_reports", "expires_at"}, rows[0]
    assert rows[0]["false_reports"] == config.FALSE_REPORTS_BEFORE_BLOCK and rows[0]["expires_at"] is None
    db = db_session()
    try:
        hashes = [b.phone_hash for b in db.query(BlockedPhone).all()]
    finally:
        db.close()
    assert hashes and not any(h in r.text or h[:8] in r.text for h in hashes)
    assert "opsphone" not in r.text
    assert client.get("/api/admin/blocked-phones", headers=second_admin()).status_code == 200  # every Admin
    assert client.get("/api/admin/blocked-phones").status_code == 401


def test_unblock_lets_the_phone_send_again_with_a_fresh_count():
    block_phone(102)
    h = admin()
    block_id = max(b["id"] for b in client.get("/api/admin/blocked-phones", headers=h).json())
    assert client.post(f"/api/admin/blocked-phones/{block_id}/unblock").status_code == 401
    r = client.post(f"/api/admin/blocked-phones/{block_id}/unblock", headers=second_admin())  # any Admin may unblock
    assert r.status_code == 200 and "again" in r.json()["message"], r.text
    assert block_id not in [b["id"] for b in client.get("/api/admin/blocked-phones", headers=h).json()]
    sent = send_hazard(102)
    assert sent.status_code == 201, sent.text
    # Fresh count: its next false report does not block it straight away.
    mark_false_via_api(sent.json()["id"], second_admin())
    assert send_hazard(102).status_code == 201
    assert client.post(f"/api/admin/blocked-phones/{block_id}/unblock", headers=h).status_code == 404
    entry = audit_rows("report.phone_unblocked")[-1]
    assert entry.actor_name == "Opsy Second Admin" and entry.target == f"blocked_phone:{block_id}"
    assert "opsphone" not in (entry.detail or "")


def test_an_expired_block_is_lifted():
    old = config.BLOCK_EXPIRES_DAYS
    config.BLOCK_EXPIRES_DAYS = 1
    try:
        block_phone(103)
        h = admin()
        assert any(b["expires_at"] for b in client.get("/api/admin/blocked-phones", headers=h).json())
        db = db_session()
        try:
            for b in db.query(BlockedPhone).all():
                b.blocked_at = b.blocked_at - timedelta(days=2)
            db.commit()
        finally:
            db.close()
        # Expired already: it no longer counts, even before the cleanup removes the row.
        assert client.get("/api/admin/blocked-phones", headers=h).json() == []
        assert send_hazard(103).status_code == 201
        db = db_session()
        try:
            assert report_service.lift_expired_blocks(db) >= 1
            assert db.query(BlockedPhone).count() == 0
        finally:
            db.close()
        assert audit_rows("report.block_expired")
        config.BLOCK_EXPIRES_DAYS = 0
        block_phone(104)  # never expires when the setting is 0
        db = db_session()
        try:
            for b in db.query(BlockedPhone).all():
                b.blocked_at = b.blocked_at - timedelta(days=999)
            db.commit()
            assert report_service.lift_expired_blocks(db) == 0
        finally:
            db.close()
        assert send_hazard(104).status_code == 403
    finally:
        config.BLOCK_EXPIRES_DAYS = old


# ------------------------------------------------------------------ 4. place edits

PLACE = {"name": "Opsy Gym A", "center_type": "temporary", "barangay": "Alangilan", "address": "Old street",
         "contact": "0900 000 0000", "max_capacity": 100, "latitude": 13.7650, "longitude": 121.0700, "note": "old note"}


def add_place(phone_n, **over):
    r = client.post("/api/evacuation-centers", headers=phone_headers(phone_n), json={**PLACE, **over})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def facility_from_api(fid, phone_n=None):
    """The place as the API lists it (a pending place only shows for the phone that added it)."""
    headers = phone_headers(phone_n) if phone_n else {}
    return next(f for f in client.get("/api/facilities", headers=headers).json() if f["id"] == fid)


def test_place_edit_needs_an_admin():
    pid = add_place(201)
    body = {"name": "Opsy Gym Renamed"}
    assert client.patch(f"/api/admin/places/{pid}", json=body).status_code == 401
    assert client.patch(f"/api/admin/places/{pid}", headers=phone_headers(201), json=body).status_code == 401


def test_place_edit_changes_details_and_audits_old_and_new():
    pid = add_place(202, name="Opsy Gym Audit", latitude=13.7701)
    h = second_admin()
    r = client.patch(f"/api/admin/places/{pid}", headers=h, json={
        "name": "  Opsy   Gym Fixed ", "address": "New street", "barangay": "Gulod", "contact": "0911 111 1111", "note": "new note"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["name"], out["address"], out["barangay"], out["contact"], out["note"]) == (
        "Opsy Gym Fixed", "New street", "Gulod", "0911 111 1111", "new note"), out
    approved = client.post(f"/api/admin/places/{pid}/approve", headers=h)
    assert approved.status_code == 200
    f = facility_from_api(pid)  # the map row is in step
    assert f["name"] == "Opsy Gym Fixed" and "New street" in f["address"] and "Gulod" in f["address"] and f["contact"] == "0911 111 1111"
    entry = [a for a in audit_rows("place.edit") if a.target.startswith(f"place:{pid} ")][-1]
    assert entry.actor_name == "Opsy Second Admin"
    detail = json.loads(entry.detail)
    assert detail["old"]["name"] == "Opsy Gym Audit" and detail["new"]["name"] == "Opsy Gym Fixed"
    assert detail["old"]["address"] == "Old street" and detail["new"]["address"] == "New street"
    # Clearing a field with an empty text; saying the same thing again changes nothing.
    r = client.patch(f"/api/admin/places/{pid}", headers=h, json={"note": ""})
    assert r.status_code == 200 and r.json()["note"] is None
    n = len(audit_rows("place.edit"))
    r = client.patch(f"/api/admin/places/{pid}", headers=h, json={"note": None})
    assert r.status_code == 200 and "Nothing changed" in r.json()["message"] and len(audit_rows("place.edit")) == n


def test_place_edit_uses_the_same_limits_as_adding():
    pid = add_place(203, name="Opsy Gym Limits", latitude=13.7712)
    h = second_admin()
    for body in ({}, {"name": None}, {"name": "x"}, {"name": "n" * 101}, {"address": "a" * 201}, {"barangay": "b" * 81},
                 {"contact": "c" * 61}, {"note": "n" * 141}, {"latitude": 13.7}, {"max_capacity": 5}):
        r = client.patch(f"/api/admin/places/{pid}", headers=h, json=body)
        assert r.status_code == 422, (body, r.status_code, r.text)
    assert client.patch(f"/api/admin/places/99999", headers=h, json={"note": "x"}).status_code == 404


def test_place_edit_applies_the_duplicate_rule_on_a_name_change():
    add_place(204, name="Opsy Duplicate Gym", latitude=13.7750, longitude=121.0800)
    pid = add_place(205, name="Opsy Other Gym", latitude=13.77505, longitude=121.08005)  # about 7 m away
    h = second_admin()
    r = client.patch(f"/api/admin/places/{pid}", headers=h, json={"name": "opsy  DUPLICATE gym!"})
    assert r.status_code == 409 and "within 30 metres" in r.json()["detail"], r.text
    assert facility_from_api(pid, 205)["name"] == "Opsy Other Gym"
    ok = client.patch(f"/api/admin/places/{pid}", headers=h, json={"name": "Opsy Not A Duplicate Gym", "note": "fine"})
    assert ok.status_code == 200, ok.text
    # A same-name center farther than 30 m is fine.
    far = add_place(206, name="Opsy Far Gym", latitude=13.7800, longitude=121.0900)
    assert client.patch(f"/api/admin/places/{far}", headers=h, json={"name": "Opsy Duplicate Gym"}).status_code == 200


def test_place_edit_refuses_hospitals_and_centers_from_the_data_files():
    h = second_admin()
    hospital = next(f for f in client.get("/api/facilities").json() if f["type"] == "hospital")
    r = client.patch(f"/api/admin/places/{hospital['id']}", headers=h, json={"note": "x"})
    assert r.status_code == 422 and "evacuation centers" in r.json()["detail"], r.text
    db = db_session()
    try:
        row = Facility(key="manual:evacuation_center:opsy-file-center", name="Opsy File Center", type="evacuation_center",
                       latitude=13.75, longitude=121.05)
        db.add(row)
        db.commit()
        fid = row.id
    finally:
        db.close()
    r = client.patch(f"/api/admin/places/{fid}", headers=h, json={"note": "x"})
    assert r.status_code == 409 and "data files" in r.json()["detail"], r.text


def test_place_edit_survives_a_restart():
    pid = add_place(207, name="Opsy Restart Gym", latitude=13.7900, longitude=121.1000)
    h = second_admin()
    assert client.patch(f"/api/admin/places/{pid}", headers=h, json={
        "name": "Opsy Restart Gym Fixed", "address": "Fixed street", "contact": "0922 222 2222"}).status_code == 200
    client.post(f"/api/admin/places/{pid}/approve", headers=h)
    # A fresh start of the app on the same database: a new process imports it, which runs the startup sync.
    code = ("from fastapi.testclient import TestClient\nfrom app.main import app\nimport json\n"
            f"f = next(x for x in TestClient(app).get('/api/facilities').json() if x['id'] == {pid})\n"
            "print(json.dumps({k: f[k] for k in ('name', 'address', 'contact')}))")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["name"] == "Opsy Restart Gym Fixed" and "Fixed street" in got["address"] and got["contact"] == "0922 222 2222", got
    main_mod.sync_facilities()  # and the same sync in this process
    assert facility_from_api(pid)["name"] == "Opsy Restart Gym Fixed"


# ------------------------------------------------------------------ 5. audit log

def test_audit_log_default_call_still_works_and_has_a_total():
    h = admin()
    r = client.get("/api/admin/audit-log", headers=h)
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()
    assert int(r.headers["X-Total-Count"]) >= len(r.json())
    assert set(r.json()[0]) == {"id", "created_at", "actor_id", "actor_name", "actor_role", "action", "target", "detail"}
    ids = [e["id"] for e in r.json()]
    assert ids == sorted(ids, reverse=True)
    old = client.get("/api/admin/audit-log", headers=h, params={"limit": 3, "before_id": ids[0], "action": "auth.sign_in"})
    assert old.status_code == 200 and all(e["action"] == "auth.sign_in" and e["id"] < ids[0] for e in old.json())
    assert client.get("/api/admin/audit-log", headers=second_admin()).status_code == 200  # every Admin
    assert client.get("/api/admin/audit-log").status_code == 401
    # The browser may read the total from another origin.
    cors = client.get("/api/admin/audit-log", headers={**h, "Origin": "http://localhost:5173"})
    assert "x-total-count" in cors.headers.get("access-control-expose-headers", "").lower()


def test_audit_log_filters_and_paging():
    for n in range(3):
        make_user(f"Opsy Filter {n}")
        sign_in(f"Opsy Filter {n}")
    h = admin()
    r = client.get("/api/admin/audit-log", headers=h, params={"person": "OPSY filter", "action": "auth.sign_in"})
    assert r.status_code == 200 and len(r.json()) == 3 and r.headers["X-Total-Count"] == "3", (r.headers["X-Total-Count"], r.text)
    assert all("Opsy Filter" in e["actor_name"] and e["action"] == "auth.sign_in" for e in r.json())
    exact = client.get("/api/admin/audit-log", headers=h, params={"actor": "Opsy Filter 1", "action": "auth.sign_in"})
    assert [e["actor_name"] for e in exact.json()] == ["Opsy Filter 1"]
    page1 = client.get("/api/admin/audit-log", headers=h, params={"person": "Opsy Filter", "action": "auth.sign_in", "limit": 2})
    page2 = client.get("/api/admin/audit-log", headers=h, params={"person": "Opsy Filter", "action": "auth.sign_in", "limit": 2, "offset": 2})
    assert len(page1.json()) == 2 and len(page2.json()) == 1
    assert page1.headers["X-Total-Count"] == page2.headers["X-Total-Count"] == "3"
    assert {e["id"] for e in page1.json()}.isdisjoint({e["id"] for e in page2.json()})
    assert client.get("/api/admin/audit-log", headers=h, params={"person": "100%"}).headers["X-Total-Count"] == "0"  # no wildcard surprises
    assert client.get("/api/admin/audit-log", headers=h, params={"offset": -1}).status_code == 422


def test_audit_log_date_filters():
    h = admin()
    db = db_session()
    try:
        row = db.query(AuditLog).filter(AuditLog.action == "auth.sign_in").order_by(AuditLog.id).first()
        rid = row.id
        row.created_at = row.created_at.replace(year=2020, month=3, day=15, hour=23, minute=59)
        db.commit()
    finally:
        db.close()
    r = client.get("/api/admin/audit-log", headers=h, params={"from": "2020-03-15", "to": "2020-03-15"})
    assert [e["id"] for e in r.json()] == [rid] and r.headers["X-Total-Count"] == "1"  # "to" includes the whole day
    assert client.get("/api/admin/audit-log", headers=h, params={"to": "2020-03-14"}).headers["X-Total-Count"] == "0"
    assert client.get("/api/admin/audit-log", headers=h, params={"from": "2020-03-16", "to": "2020-03-31"}).json() == []
    late = client.get("/api/admin/audit-log", headers=h, params={"from": "2020-03-16"})
    assert rid not in [e["id"] for e in late.json()]
    for bad in ("31-12-2026", "tomorrow", "2026-13-01", "2026-02-30"):
        r = client.get("/api/admin/audit-log", headers=h, params={"from": bad})
        assert r.status_code == 422 and "year-month-day" in r.json()["detail"] and "Traceback" not in r.text, (bad, r.text)
        assert client.get("/api/admin/audit-log", headers=h, params={"to": bad}).status_code == 422
    r = client.get("/api/admin/audit-log", headers=h, params={"from": "2026-05-02", "to": "2026-05-01"})
    assert r.status_code == 422 and "later" in r.json()["detail"]


# ------------------------------------------------------------------ 6. scheduled cleanup

def test_cleanup_runs_every_job_once_when_called():
    db = db_session()
    try:
        u = db.query(User).filter(User.name == "Opsy Admin").first()
        old = report_service._now() - timedelta(days=config.REPORTS_KEEP_DAYS + 5)
        db.add(Report(kind="help", status="new", phone_hash="x" * 64, ip_hash="y", latitude=13.7, longitude=121.0,
                      contact="c", created_at=old, updated_at=old))
        db.add(AuthSession(token_hash="opsy-dead-session", user_id=u.id, created_at=old, last_used_at=old))
        db.commit()
        before = db.query(Report).count()
    finally:
        db.close()
    results = maintenance.run_jobs()
    assert set(results) == {"reports", "removed_places", "sessions", "phone_blocks"}, results
    assert results["reports"] >= 1 and results["sessions"] >= 1 and all(v is not None for v in results.values()), results
    db = db_session()
    try:
        assert db.query(Report).count() == before - results["reports"]
        assert db.query(AuthSession).filter(AuthSession.token_hash == "opsy-dead-session").count() == 0
    finally:
        db.close()


def test_cleanup_keeps_going_after_a_job_fails_and_logs_no_data():
    seen = []

    def boom(db):
        raise RuntimeError("SECRET-DATA 0900 000 0000")

    def fine(db):
        seen.append("ran")
        return 4

    saved = list(maintenance.JOBS)
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage() + (record.exc_text or "") + str(record.exc_info))

    handler = Catch(level=logging.DEBUG)
    maintenance.log.addHandler(handler)
    maintenance.log.setLevel(logging.DEBUG)
    maintenance.JOBS[:] = [("first_breaks", boom), ("second_works", fine), ("third_works", fine)]
    try:
        results = maintenance.run_jobs()
    finally:
        maintenance.JOBS[:] = saved
        maintenance.log.removeHandler(handler)
    assert results == {"first_breaks": None, "second_works": 4, "third_works": 4}, results
    assert seen == ["ran", "ran"]
    text = " ".join(records)
    assert "first_breaks" in text and "second_works" in text and "4" in text
    assert "SECRET-DATA" not in text and "0900" not in text and "Traceback" not in text


def test_cleanup_loop_runs_repeatedly_stops_cleanly_and_is_off_at_zero():
    assert config.PURGE_INTERVAL_MINUTES == 0  # the tests turn it off

    async def scenario():
        from app.maintenance import Scheduler
        s = Scheduler()
        assert await s.start() is False and not s.running  # interval 0 = off
        calls = []
        saved = list(maintenance.JOBS)
        maintenance.JOBS[:] = [("count", lambda db: calls.append(1) or 0)]
        try:
            assert await s.start(interval_seconds=0.05) is True and s.running
            await asyncio.sleep(0.4)
            await asyncio.wait_for(s.stop(), timeout=5)
        finally:
            maintenance.JOBS[:] = saved
        n = len(calls)
        assert n >= 2 and not s.running, (n, s.running)
        await asyncio.sleep(0.2)
        assert len(calls) == n  # nothing runs after stop

    asyncio.run(scenario())
    with TestClient(app):  # the real startup and shutdown of the app: no task is started
        assert not maintenance.scheduler.running


# ------------------------------------------------------------------ 7. demo data script

def _seed(args, cwd, extra_env=None, drop=("DATABASE_URL",)):
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(extra_env or {})
    return subprocess.run([sys.executable, str(BACKEND / "scripts" / "seed_demo.py"), *args], cwd=cwd,
                          env=env, capture_output=True, text=True)


def _counts(db_file):
    c = sqlite3.connect(db_file)
    try:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("reports", "user_evacuation_centers", "advisories", "users", "facilities", "audit_log")}
    finally:
        c.close()


def test_seed_refuses_the_default_database_without_force():
    d = Path(tempfile.mkdtemp())
    r = _seed([], d)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "Database:" in r.stdout and "typhoon.db" in r.stdout and "Refusing" in r.stdout
    assert not (d / "typhoon.db").exists()  # nothing was even created
    r = _seed(["--with-demo-staff"], d)
    assert r.returncode == 2 and not (d / "typhoon.db").exists()
    # A database server is treated as real too, and its password is never printed.
    r = _seed([], d, {"DATABASE_URL": "postgresql://someone:hunter2pw@localhost/silong"})
    assert r.returncode == 2 and "hunter2pw" not in r.stdout + r.stderr and "Database:" in r.stdout
    # --force allows it (here in a throw-away folder).
    r = _seed(["--force"], d)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (d / "typhoon.db").exists()


def test_seed_into_a_separate_file_is_safe_to_run_twice():
    d = Path(tempfile.mkdtemp())
    db_file = d / "demo.db"
    first = _seed(["--db", str(db_file), "--with-demo-staff"], d)
    assert first.returncode == 0, (first.stdout, first.stderr)
    assert "demo.db" in first.stdout.split("\n")[0]
    passwords = [line.split("password: ")[1] for line in first.stdout.splitlines() if "password: " in line]
    assert len(passwords) == 2 and all(len(p) >= config.MIN_PASSWORD_LENGTH for p in passwords)
    c1 = _counts(db_file)
    assert c1["reports"] >= 8 and c1["user_evacuation_centers"] >= 4 and c1["advisories"] >= 3 and c1["users"] == 2
    second = _seed(["--db", str(db_file), "--with-demo-staff"], d)
    assert second.returncode == 0, (second.stdout, second.stderr)
    assert _counts(db_file) == c1  # no duplicates
    assert not any(p in second.stdout for p in passwords)  # a password is shown once, when it is made
    assert not (d / "typhoon.db").exists()
    # DEMO data is marked, and the shapes the screens need are there.
    c = sqlite3.connect(db_file)
    try:
        notes = [n for (n,) in c.execute("SELECT note FROM reports")]
        assert all(n.startswith("DEMO") for n in notes)
        assert c.execute("SELECT COUNT(*) FROM advisories WHERE pinned = 1").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM reports WHERE verified_at IS NOT NULL").fetchone()[0] >= 1
        assert c.execute("SELECT MAX(n) FROM (SELECT COUNT(DISTINCT phone_hash) n FROM reports WHERE kind='hazard' GROUP BY group_id)").fetchone()[0] == 3
        states = {s for (s,) in c.execute("SELECT approval_status FROM user_evacuation_centers")}
        assert states == {"approved", "pending"}
    finally:
        c.close()
    # Without --with-demo-staff no accounts are made.
    d2 = Path(tempfile.mkdtemp())
    assert _seed(["--db", str(d2 / "x.db")], d2).returncode == 0 and _counts(d2 / "x.db")["users"] == 0
    # DATABASE_URL works as well as --db.
    d3 = Path(tempfile.mkdtemp())
    r = _seed([], d3, {"DATABASE_URL": f"sqlite:///{d3 / 'viaenv.db'}"})
    assert r.returncode == 0 and (d3 / "viaenv.db").exists(), (r.stdout, r.stderr)


# ------------------------------------------------------------------ 8. API document

def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_api_doc_under_test", BACKEND / "scripts" / "generate_api_doc.py")
    return spec, importlib.util.module_from_spec(spec)


def app_routes():
    """(METHOD, path) of every route, taken from the routers themselves (not from the OpenAPI schema)."""
    from app import account_routes, chat_routes, content_routes, evac_routes, ops_routes, place_routes, report_routes
    found = set()
    sources = [m.router.routes for m in (account_routes, chat_routes, content_routes, evac_routes, ops_routes, place_routes, report_routes)]
    sources.append([r for r in app.router.routes if hasattr(r, "methods") and hasattr(r, "path")])
    for routes in sources:
        for r in routes:
            if getattr(r, "include_in_schema", False):
                found |= {(m, r.path) for m in r.methods if m != "HEAD"}
    return found


def test_api_document_lists_every_route():
    routes = app_routes()
    assert len(routes) >= 50, len(routes)
    out = Path(tempfile.mkdtemp()) / "API.md"
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "generate_api_doc.py"), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for label, text in (("fresh", out.read_text(encoding="utf-8")), ("committed docs/API.md", (REPO / "docs" / "API.md").read_text(encoding="utf-8"))):
        missing = sorted(f"{m} {p}" for m, p in routes if f"### `{m} {p}`" not in text)
        assert not missing, f"{label} is missing routes: {missing}"
        for needle in ("X-Phone-Id", "Bearer", "30 minutes", "401", "403", "422", "423", "429",
                       "Example flows", "/api/auth/change-password", "X-Total-Count", "Shapes used above"):
            assert needle in text, (label, needle)
        assert "| ? |" not in text and "(?" not in text  # every endpoint has a "who can call it"
    fresh = out.read_text(encoding="utf-8")
    assert "| `POST` | `/api/admin/users/{user_id}/reset-password` | Admin |" in fresh
    assert "| `PATCH` | `/api/admin/places/{facility_id}` | Admin |" in fresh
    assert "| `POST` | `/api/admin/reports/{report_id}/take` | Admin |" in fresh
    for label, text in (("fresh", fresh), ("committed docs/API.md", (REPO / "docs" / "API.md").read_text(encoding="utf-8"))):
        assert "/api/responder" not in text and "Super admin" not in text and "Responder" not in text, label
    assert "| `POST` | `/api/reports` | Public (X-Phone-Id required) |" in fresh


# ------------------------------------------------------------------ nothing else changed

def test_existing_endpoints_still_work():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/facilities").status_code == 200
    assert client.get("/api/emergency-numbers").status_code == 200
    h = admin()
    assert client.get("/api/me", headers=h).status_code == 200
    assert client.get("/api/admin/users", headers=h).status_code == 200


def run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items(), key=lambda kv: list(globals()).index(kv[0])) if n.startswith("test_") and callable(f)]
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
