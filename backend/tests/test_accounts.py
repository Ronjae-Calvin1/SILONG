"""
Part 1 checks: Admin accounts (one role), lockout, idle timeout, audit log, the role migration.

Run from the backend folder (needs `pip install -r requirements-dev.txt` once):

    py tests/test_accounts.py

It uses its own temporary database, so typhoon.db is never touched. (pytest
also works: `py -m pytest tests -q`, if you have it installed.)
"""
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

# Must be set BEFORE the app is imported: own database, no limits in the way.
_tmp = tempfile.mkdtemp(prefix="silong-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "1000"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, config  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, AuthSession, User  # noqa: E402
from app.rate_limit import signin_limiter  # noqa: E402
import route_helpers  # noqa: E402  (tests/route_helpers.py: finds every route of the app)

client = TestClient(app)
PASSWORD = "correct horse 1"


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


def audit_actions():
    db = db_session()
    try:
        return [(a.actor_name, a.action, a.target) for a in db.query(AuditLog).order_by(AuditLog.id).all()]
    finally:
        db.close()


# Two Admins shared by the checks below.
ADMIN_ID = make_user("Admin Ana")
ADMIN_B_ID = make_user("Rey Admin")


def test_existing_endpoints_still_work_without_a_token():
    assert client.get("/api/health").status_code == 200
    facilities = client.get("/api/facilities")
    assert facilities.status_code == 200 and len(facilities.json()) > 0
    fid = facilities.json()[0]["id"]
    assert client.get(f"/api/facilities/{fid}/status/history").status_code == 200
    # Part 3: the list of removed centers is for staff now (nothing public in the frontend calls it).
    assert client.get("/api/evacuation-centers/removed").status_code == 401


def admin_routes():
    """
    (METHOD, path, route) of every route that needs an Admin, wherever it is defined: found through the
    dependencies of ALL the app's routes (tests/route_helpers.py), so a route or a whole router added
    later is covered without touching this test. (It used to read six hand-listed router modules and
    missed console_routes and settings_routes.)
    """
    return [(m, p, r) for m, p, r in route_helpers.all_routes(app) if route_helpers.kind_of(r) == "admin"]


def fill(path):
    """A path with its {parameters} filled in (any id: the check runs before the thing is looked up)."""
    import re
    return re.sub(r"\{[^}]+\}", "1", path)


def test_the_admin_route_list_is_complete():
    routes = {(m, p) for m, p, _ in admin_routes()}
    assert len(routes) >= 44, len(routes)
    # No old path is left, and every route staff used under /api/responder is under /api/admin now.
    assert not any("/api/responder" in p for _, p in routes)
    for needle in [
        ("GET", "/api/me"), ("GET", "/api/admin/users"), ("GET", "/api/admin/audit-log"),
        ("GET", "/api/admin/reports"), ("POST", "/api/admin/reports/{report_id}/take"),
        ("GET", "/api/admin/places"), ("PATCH", "/api/admin/places/{facility_id}"), ("DELETE", "/api/admin/places/{facility_id}"),
        ("POST", "/api/admin/facilities/{facility_id}/status-override"),
        ("POST", "/api/admin/facilities/{facility_id}/capacity-correction"),
        ("GET", "/api/admin/facilities/{facility_id}/status-history"),
        ("POST", "/api/admin/advisories"), ("GET", "/api/admin/advisory-sources"), ("PUT", "/api/admin/emergency-numbers/order"),
        ("GET", "/api/admin/blocked-phones"), ("POST", "/api/admin/blocked-phones/{block_id}/unblock"),
        ("GET", "/api/evacuation-centers/removed"), ("DELETE", "/api/evacuation-centers/{facility_id}"),
        # these four live in console_routes.py and settings_routes.py, which the old sweep did not read
        ("GET", "/api/admin/summary"), ("GET", "/api/admin/me/activity"),
        ("GET", "/api/admin/contact-settings"), ("PATCH", "/api/admin/contact-settings"),
    ]:
        assert needle in routes, needle


def test_the_route_table_is_complete():
    """The sweeps below can only check routes they can see: the route finder must agree with the app's own OpenAPI list."""
    found = {(m, p) for m, p, _ in route_helpers.all_routes(app)}
    assert found == route_helpers.openapi_operations(app), found ^ route_helpers.openapi_operations(app)


def test_every_route_under_api_admin_has_an_admin_dependency():
    """
    The second guard: a route whose path says /api/admin but that does not depend on require_admin
    (forgotten, or using only current_user / optional_staff) would be open to everyone. Fails by name.
    The 401/403 behaviour of the admin routes is checked by the sweeps below, not here.
    """
    under_admin = [(m, p, r) for m, p, r in route_helpers.all_routes(app) if p == "/api/admin" or p.startswith("/api/admin/")]
    assert len(under_admin) >= 35, len(under_admin)
    open_ones = [f"{m} {p} ({route_helpers.kind_of(r)})" for m, p, r in under_admin if route_helpers.kind_of(r) != "admin"]
    assert not open_ones, "no require_admin on: " + ", ".join(open_ones)


def test_every_admin_route_is_401_without_a_good_sign_in():
    """No token, a made-up token, a malformed header and a signed-out token: always 401, never 403 or a 5xx."""
    h = auth("Rey Admin")
    assert client.post("/api/auth/sign-out", headers=h).status_code == 200  # h is a dead token now
    bad = [{}, {"Authorization": "Bearer not-a-real-token"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}, h]
    for method, path, _ in admin_routes():
        for headers in bad:
            r = client.request(method, fill(path), headers=headers)
            assert r.status_code == 401, f"{method} {path} gave {r.status_code} for {headers}"
            assert r.headers.get("www-authenticate") == "Bearer"


def test_every_admin_route_is_403_for_a_locked_or_removed_account():
    """
    A sign-in that is still alive but whose account was locked or removed some other way than the
    API (the API ends the sessions itself, which is a 401): 403, and the sign-in is gone afterwards.
    """
    n = 0
    for case in ("locked", "removed"):
        for method, path, _ in admin_routes():
            n += 1
            name = f"Gone {case} {n}"
            uid = make_user(name)
            h = auth(name)
            db = db_session()
            try:
                if case == "locked":
                    db.get(User, uid).is_locked = True
                else:
                    db.delete(db.get(User, uid))  # the session row stays: it points at nobody
                db.commit()
            finally:
                db.close()
            r = client.request(method, fill(path), headers=h)
            assert r.status_code == 403, f"{case}: {method} {path} gave {r.status_code}"
            assert client.request(method, fill(path), headers=h).status_code == 401  # the sign-in was deleted


def test_every_admin_route_lets_a_second_admin_in():
    """Nothing is locked by role: a plain Admin gets past the sign-in check on every admin route (it is never 401 or 403)."""
    h = auth("Rey Admin")
    skip = {("DELETE", "/api/admin/users/{user_id}"), ("POST", "/api/admin/users/{user_id}/lock")}  # these would change the shared accounts
    for method, path, _ in admin_routes():
        if (method, path) in skip:
            continue
        r = client.request(method, fill(path), headers=h)
        assert r.status_code not in (401, 403), f"{method} {path} gave {r.status_code}: {r.text[:120]}"


def test_me_and_the_one_role():
    me = client.get("/api/me", headers=auth("Rey Admin")).json()
    assert me["name"] == "Rey Admin" and me["role"] == "admin"
    me = client.get("/api/me", headers=auth("admin ana")).json()  # name is not case sensitive
    assert me["role"] == "admin" and me["idle_timeout_minutes"] == config.STAFF_IDLE_MINUTES
    listed = client.get("/api/admin/users", headers=auth("Admin Ana")).json()
    assert listed and all(u["role"] == "admin" for u in listed)


def test_any_admin_can_use_the_account_routes():
    """What only a Super admin could do is open to every Admin, and each change is logged under that Admin's name."""
    h = auth("Rey Admin")
    assert client.get("/api/admin/users", headers=h).status_code == 200
    assert client.get("/api/admin/audit-log", headers=h).status_code == 200
    r = client.post("/api/admin/users", headers=h, json={"name": "Made By Rey", "password": PASSWORD})
    assert r.status_code == 201 and r.json()["role"] == "admin" and r.json()["created_by"] == "Rey Admin"
    uid = r.json()["id"]
    assert client.post(f"/api/admin/users/{uid}/lock", headers=h).json()["status"] == "locked_by_admin"
    assert client.post(f"/api/admin/users/{uid}/unlock", headers=h).json()["status"] == "active"
    assert client.post(f"/api/admin/users/{uid}/reset-password", headers=h, json={"new_password": "another pass 2"}).status_code == 200
    assert client.delete(f"/api/admin/users/{uid}", headers=h).status_code == 200
    mine = [a for a in audit_actions() if a[0] == "Rey Admin"]
    for action in ("user.create", "user.lock", "user.unlock", "user.reset_password", "user.remove"):
        assert any(a[1] == action for a in mine), action


def test_legacy_role_in_account_creation_is_ignored():
    h = auth("Admin Ana")
    for n, legacy in enumerate(("responder", "super_admin", "admin")):
        r = client.post("/api/admin/users", headers=h, json={"name": f"Legacy Role {n}", "password": PASSWORD, "role": legacy})
        assert r.status_code == 201, r.text
        assert r.json()["role"] == "admin" and "ignored" in r.json()["message"]
    plain = client.post("/api/admin/users", headers=h, json={"name": "No Role Sent", "password": PASSWORD})
    assert plain.status_code == 201 and plain.json()["role"] == "admin" and plain.json()["message"] is None
    # Any other value is still a 422, and so is any other unknown field.
    assert client.post("/api/admin/users", headers=h, json={"name": "King", "password": PASSWORD, "role": "king"}).status_code == 422
    assert client.post("/api/admin/users", headers=h, json={"name": "Extra", "password": PASSWORD, "is_boss": True}).status_code == 422
    db = db_session()
    try:
        stored = {u.name: u.role for u in db.query(User).filter(User.name.like("Legacy Role%") | (User.name == "No Role Sent")).all()}
        assert set(stored.values()) == {"admin"} and len(stored) == 4
    finally:
        db.close()
    create = [e for e in client.get("/api/admin/audit-log?action=user.create&limit=200", headers=h).json() if "Legacy Role 0" in e["target"]][0]
    assert create["detail"]["role"] == "admin" and create["actor_role"] == "admin"


def test_lockout_after_five_wrong_tries_and_unlock():
    uid = make_user("Lock Test")
    for i in range(config.SIGNIN_MAX_WRONG_TRIES - 1):
        r = sign_in("Lock Test", "wrong password")
        assert r.status_code == 401, (i, r.status_code)
    r = sign_in("Lock Test", "wrong password")  # the 5th wrong try locks it
    assert r.status_code == 423 and "locked" in r.json()["detail"].lower()
    # even the right password is refused while locked
    r = sign_in("Lock Test", PASSWORD)
    assert r.status_code == 423

    # an Admin sees it as locked, then unlocks it
    admin = auth("Admin Ana")
    listed = {u["id"]: u for u in client.get("/api/admin/users", headers=admin).json()}
    assert listed[uid]["status"] == "locked_for_wrong_tries"
    r = client.post(f"/api/admin/users/{uid}/unlock", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert sign_in("Lock Test", PASSWORD).status_code == 200


def test_lock_runs_out_after_the_lock_time():
    make_user("Timed Lock")
    for _ in range(config.SIGNIN_MAX_WRONG_TRIES):
        sign_in("Timed Lock", "nope nope nope")
    assert sign_in("Timed Lock", PASSWORD).status_code == 423
    db = db_session()  # pretend the 15 minutes have passed
    try:
        u = db.query(User).filter(User.name == "Timed Lock").one()
        assert u.locked_until is not None
        u.locked_until = u.locked_until - timedelta(minutes=config.SIGNIN_LOCK_MINUTES + 1)
        db.commit()
    finally:
        db.close()
    assert sign_in("Timed Lock", PASSWORD).status_code == 200


def test_wrong_tries_in_a_row_reset_after_a_good_sign_in():
    make_user("Reset Test")
    for _ in range(config.SIGNIN_MAX_WRONG_TRIES - 1):
        assert sign_in("Reset Test", "bad bad bad").status_code == 401
    assert sign_in("Reset Test", PASSWORD).status_code == 200
    for _ in range(config.SIGNIN_MAX_WRONG_TRIES - 1):  # not locked: the count started again
        assert sign_in("Reset Test", "bad bad bad").status_code == 401
    assert sign_in("Reset Test", PASSWORD).status_code == 200


def test_unknown_name_and_wrong_password_look_the_same():
    a = sign_in("Nobody Here", PASSWORD)
    b = sign_in("Rey Admin", "wrong password")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_idle_timeout():
    make_user("Idle Test")
    h = auth("Idle Test")
    assert client.get("/api/me", headers=h).status_code == 200

    # Use keeps the session alive: 20 idle minutes is fine, and the timer restarts.
    _age_session("Idle Test", minutes=20)
    assert client.get("/api/me", headers=h).status_code == 200
    _age_session("Idle Test", minutes=20)
    assert client.get("/api/me", headers=h).status_code == 200

    # 31 minutes without use ends it, and it stays ended.
    _age_session("Idle Test", minutes=config.STAFF_IDLE_MINUTES + 1)
    r = client.get("/api/me", headers=h)
    assert r.status_code == 401 and "without use" in r.json()["detail"]
    assert client.get("/api/me", headers=h).status_code == 401
    assert sign_in("Idle Test").status_code == 200  # signing in again works


def _age_session(name, minutes):
    db = db_session()
    try:
        uid = db.query(User).filter(User.name == name).one().id
        for s in db.query(AuthSession).filter(AuthSession.user_id == uid).all():
            s.last_used_at = s.last_used_at - timedelta(minutes=minutes)
        db.commit()
    finally:
        db.close()


def test_sign_out_ends_the_session():
    make_user("Out Test")
    h = auth("Out Test")
    assert client.post("/api/auth/sign-out", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/auth/sign-out", headers=h).status_code == 200  # twice is fine
    assert client.post("/api/auth/sign-out").status_code == 200  # no token is fine too


def test_admin_creates_locks_unlocks_removes():
    admin = auth("Admin Ana")
    r = client.post("/api/admin/users", headers=admin, json={"name": "New Person", "password": PASSWORD})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert "password" not in r.text and "hash" not in r.text
    dup = client.post("/api/admin/users", headers=admin, json={"name": "new  PERSON", "password": PASSWORD})
    assert dup.status_code == 409
    short = client.post("/api/admin/users", headers=admin, json={"name": "Short Pw", "password": "abc"})
    assert short.status_code == 422
    bad_role = client.post("/api/admin/users", headers=admin, json={"name": "Bad Role", "password": PASSWORD, "role": "king"})
    assert bad_role.status_code == 422

    person = auth("New Person")
    assert client.get("/api/me", headers=person).status_code == 200

    # locking signs them out at once and blocks new sign-ins
    assert client.post(f"/api/admin/users/{uid}/lock", headers=admin).json()["status"] == "locked_by_admin"
    assert client.get("/api/me", headers=person).status_code == 401
    assert sign_in("New Person").status_code == 423
    assert client.post(f"/api/admin/users/{uid}/unlock", headers=admin).json()["status"] == "active"
    assert sign_in("New Person").status_code == 200

    # you cannot lock or remove yourself
    assert client.post(f"/api/admin/users/{ADMIN_ID}/lock", headers=admin).status_code == 409
    assert client.delete(f"/api/admin/users/{ADMIN_ID}", headers=admin).status_code == 409
    assert client.post("/api/admin/users/99999/lock", headers=admin).status_code == 404

    # removing deletes the account and ends its sessions
    person = auth("New Person")
    assert client.delete(f"/api/admin/users/{uid}", headers=admin).status_code == 200
    assert client.get("/api/me", headers=person).status_code == 401
    assert sign_in("New Person").status_code == 401


def test_passwords_are_stored_hashed():
    db = db_session()
    try:
        for u in db.query(User).all():
            assert PASSWORD not in u.password_hash and u.password_hash.startswith("scrypt$")
    finally:
        db.close()
    # the token sent to the browser is not what is stored: only its hash is
    from app.security import hash_token
    token = sign_in("Rey Admin").json()["token"]
    db = db_session()
    try:
        assert db.query(AuthSession).filter(AuthSession.token_hash == token).count() == 0
        assert db.query(AuthSession).filter(AuthSession.token_hash == hash_token(token)).count() == 1
    finally:
        db.close()


def test_audit_entries_are_written_with_names():
    admin = auth("Admin Ana")
    log = client.get("/api/admin/audit-log?limit=200", headers=admin).json()
    seen = {(e["actor_name"], e["action"]) for e in log}
    assert ("Admin Ana", "user.create") in seen
    assert ("Admin Ana", "user.lock") in seen
    assert ("Admin Ana", "user.unlock") in seen
    assert ("Admin Ana", "user.remove") in seen
    assert ("Admin Ana", "auth.sign_in") in seen
    assert ("Lock Test", "auth.auto_lock") in seen
    assert ("Out Test", "auth.sign_out") in seen
    assert ("test setup", "user.create") in seen  # made outside the API, still logged by name
    removed = [e for e in log if e["action"] == "user.remove"][0]
    assert "New Person" in removed["target"]  # the entry still reads correctly after removal
    # newest first, filters and paging work, and no password or token leaks into the log
    ids = [e["id"] for e in log]
    assert ids == sorted(ids, reverse=True)
    only = client.get("/api/admin/audit-log?action=user.lock", headers=admin).json()
    assert only and all(e["action"] == "user.lock" for e in only)
    page = client.get(f"/api/admin/audit-log?limit=2&before_id={ids[0]}", headers=admin).json()
    assert len(page) == 2 and all(e["id"] < ids[0] for e in page)
    mine = client.get("/api/admin/audit-log?actor=admin ana", headers=admin)
    assert mine.status_code == 200
    assert PASSWORD not in client.get("/api/admin/audit-log?limit=200", headers=admin).text


def test_audit_helper_for_later_parts():
    from app import audit
    db = db_session()
    try:
        user = db.query(User).filter(User.name == "Rey Admin").one()
        audit.record(db, user, "report.resolve", target="report:12", detail={"note": "Team sent"})
        db.commit()
    finally:
        db.close()
    entry = client.get("/api/admin/audit-log?action=report.resolve", headers=auth("Admin Ana")).json()[0]
    assert entry["actor_name"] == "Rey Admin" and entry["actor_role"] == "admin"
    assert entry["target"] == "report:12" and entry["detail"] == {"note": "Team sent"}


def test_first_admin_setup_refuses_a_second():
    db = db_session()
    try:
        try:
            accounts.create_first_admin(db, "Another Admin", PASSWORD)
        except accounts.AccountError as e:
            assert e.status_code == 409 and "Admin already exists" in e.detail
        else:
            raise AssertionError("a second first Admin was allowed")
    finally:
        db.close()


def test_create_admin_script_makes_the_first_admin_only():
    """scripts/create_admin.py: asks for a name and a password twice, makes one Admin, refuses a second run. The old script is gone."""
    import subprocess
    backend = Path(__file__).resolve().parent.parent
    assert not (backend / "scripts" / "create_super_admin.py").exists()
    d = Path(tempfile.mkdtemp())
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{d / 'first.db'}"}
    code = (
        "import getpass, runpy, sys\n"
        "answers = iter(['first password 1', 'first password 1'])\n"
        "getpass.getpass = lambda prompt='': next(answers)\n"
        "import builtins; builtins.input = lambda prompt='': 'First Admin'\n"
        f"sys.argv = [r'{backend / 'scripts' / 'create_admin.py'}']\n"
        f"runpy.run_path(r'{backend / 'scripts' / 'create_admin.py'}', run_name='__main__')\n"
    )
    first = subprocess.run([sys.executable, "-c", code], cwd=d, env=env, capture_output=True, text=True)
    assert first.returncode == 0 and "Admin 'First Admin' was created" in first.stdout, (first.stdout, first.stderr)
    second = subprocess.run([sys.executable, "-c", code], cwd=d, env=env, capture_output=True, text=True)
    assert second.returncode == 1 and "An Admin already exists" in second.stdout, (second.stdout, second.stderr)
    import sqlite3
    con = sqlite3.connect(d / "first.db")
    try:
        assert con.execute("SELECT name, role FROM users").fetchall() == [("First Admin", "admin")]
        assert con.execute("SELECT actor_name, action FROM audit_log WHERE action = 'user.create'").fetchall() == [("setup script", "user.create")]
    finally:
        con.close()


def _insert_legacy(name, role):
    """An account as an older database holds it: made by raw SQL, with an old role."""
    db = db_session()
    try:
        from sqlalchemy import text
        db.execute(text(
            "INSERT INTO users (name, name_key, password_hash, role, failed_attempts, is_locked, created_at) "
            "VALUES (:n, :k, 'x', :r, 0, 0, datetime('now'))"), {"n": name, "k": accounts.normalize_name(name), "r": role})
        db.commit()
        return db.query(User).filter(User.name == name).one().id
    finally:
        db.close()


def test_migration_turns_old_roles_into_admin_and_is_idempotent():
    old_a = _insert_legacy("Old Responder Migrate", "responder")
    old_b = _insert_legacy("Old Super Migrate", "super_admin")
    db = db_session()
    try:
        assert accounts.migrate_roles(db) == 2
        roles = {u.name: u.role for u in db.query(User).all()}
        assert roles["Old Responder Migrate"] == roles["Old Super Migrate"] == "admin"
        assert set(roles.values()) == {"admin"}
        # Logged: one audit entry per account, by "(system)", with the old role. Nothing else changed.
        rows = db.query(AuditLog).filter(AuditLog.action == "user.role_migrated").order_by(AuditLog.id).all()
        got = {r.target: (r.actor_name, r.detail) for r in rows}
        assert got[f"user:{old_a} (Old Responder Migrate)"] == ("(system)", '{"from": "responder", "to": "admin"}')
        assert got[f"user:{old_b} (Old Super Migrate)"][1] == '{"from": "super_admin", "to": "admin"}'
        # Again: nothing to do, nothing written.
        before = db.query(AuditLog).count()
        assert accounts.migrate_roles(db) == 0 and db.query(AuditLog).count() == before
    finally:
        db.close()
    # A migrated account signs in (a real password is needed, so set one) and can use every admin route.
    db = db_session()
    try:
        from app.security import hash_password
        db.get(User, old_a).password_hash = hash_password(PASSWORD)
        db.commit()
    finally:
        db.close()
    h = auth("Old Responder Migrate")
    assert client.get("/api/me", headers=h).json()["role"] == "admin"
    assert client.get("/api/admin/audit-log", headers=h).status_code == 200


def test_migration_runs_on_startup_against_an_old_database():
    """An existing typhoon.db with old roles keeps its accounts and data; starting the app twice is safe."""
    import sqlite3
    import subprocess
    backend = Path(__file__).resolve().parent.parent
    d = Path(tempfile.mkdtemp())
    dbfile = d / "old.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}
    code = "import sys; sys.path.insert(0, r'%s'); import app.main" % backend
    assert subprocess.run([sys.executable, "-c", code], cwd=d, env=env, capture_output=True, text=True).returncode == 0
    con = sqlite3.connect(dbfile)
    try:
        for n, role in enumerate(("responder", "super_admin", "responder")):
            con.execute("INSERT INTO users (name, name_key, password_hash, role, failed_attempts, is_locked, created_at) "
                        "VALUES (?, ?, 'x', ?, 0, 0, datetime('now'))", (f"Old {n}", f"old {n}", role))
        con.execute("INSERT INTO audit_log (actor_name, actor_role, action, created_at) VALUES ('Old 1', 'super_admin', 'user.create', datetime('now'))")
        con.commit()
    finally:
        con.close()
    for _ in range(2):  # the second start must change nothing
        r = subprocess.run([sys.executable, "-c", code], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(dbfile)
        try:
            assert con.execute("SELECT name, role FROM users ORDER BY id").fetchall() == [("Old 0", "admin"), ("Old 1", "admin"), ("Old 2", "admin")]
            assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'user.role_migrated'").fetchone()[0] == 3
            # History is never rewritten: the old entry still says what the role was then.
            assert con.execute("SELECT actor_role FROM audit_log WHERE action = 'user.create'").fetchone()[0] == "super_admin"
        finally:
            con.close()


def test_the_last_active_admin_cannot_be_locked_or_removed():
    db = db_session()
    try:
        # Everyone else is locked, so "Solo Admin" is the last active Admin; the actor is a locked one (only reachable outside the API).
        solo = accounts.create_user(db, "Solo Admin", PASSWORD, actor="test setup")
        ghost = accounts.create_user(db, "Locked Actor", PASSWORD, actor="test setup")
        others = [u for u in db.query(User).filter(User.id.notin_([solo.id, ghost.id])).all()]
        for u in others:
            u.is_locked = True
        ghost.is_locked = True
        db.commit()
        assert accounts.active_admin_count(db) == 1
        for action in (accounts.lock_user, accounts.remove_user):
            try:
                action(db, ghost, solo)
            except accounts.AccountError as e:
                assert e.status_code == 409 and "last active Admin" in e.detail, e.detail
            else:
                raise AssertionError(f"{action.__name__} allowed the last active Admin")
        assert not db.get(User, solo.id).is_locked
        # Yourself first: the self check still comes before the last-Admin check.
        try:
            accounts.lock_user(db, solo, solo)
        except accounts.AccountError as e:
            assert "your own" in e.detail
        # With another active Admin around, locking is allowed again.
        for u in others:
            u.is_locked = False
        db.commit()
        assert accounts.lock_user(db, ghost, solo) is True
        accounts.unlock_user(db, ghost, solo)
    finally:
        db.close()


def test_the_last_admin_rule_over_the_api():
    """Through the API you cannot even reach it (you are the other active Admin), and yourself is still refused."""
    h = auth("Admin Ana")
    assert client.post(f"/api/admin/users/{ADMIN_ID}/lock", headers=h).status_code == 409
    assert client.delete(f"/api/admin/users/{ADMIN_ID}", headers=h).status_code == 409


def test_sign_in_ip_limit():
    signin_limiter.reset()
    old = config.SIGNIN_IP_MAX_ATTEMPTS
    config.SIGNIN_IP_MAX_ATTEMPTS = 3
    try:
        codes = [sign_in("Nobody Here", "whatever").status_code for _ in range(4)]
        assert codes == [401, 401, 401, 429], codes
    finally:
        config.SIGNIN_IP_MAX_ATTEMPTS = old
        signin_limiter.reset()


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
