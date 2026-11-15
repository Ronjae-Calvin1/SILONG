"""
Part 1 checks: accounts, roles, lockout, idle timeout, audit log.

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

client = TestClient(app)
PASSWORD = "correct horse 1"


def db_session():
    return SessionLocal()


def make_user(name, role, password=PASSWORD):
    db = db_session()
    try:
        return accounts.create_user(db, name, password, role, actor="test setup").id
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


# One Super admin and one responder shared by the checks below.
ADMIN_ID = make_user("Admin Ana", "super_admin")
RESP_ID = make_user("Rey Responder", "responder")


def test_existing_endpoints_still_work_without_a_token():
    assert client.get("/api/health").status_code == 200
    facilities = client.get("/api/facilities")
    assert facilities.status_code == 200 and len(facilities.json()) > 0
    fid = facilities.json()[0]["id"]
    assert client.get(f"/api/facilities/{fid}/status/history").status_code == 200
    assert client.get("/api/evacuation-centers/removed").status_code == 200


def test_no_token_is_blocked():
    for method, path in [
        ("get", "/api/me"), ("get", "/api/admin/users"), ("get", "/api/admin/audit-log"),
        ("post", "/api/admin/users"), ("post", "/api/admin/users/1/lock"),
        ("post", "/api/admin/users/1/unlock"), ("delete", "/api/admin/users/1"),
    ]:
        r = getattr(client, method)(path)
        assert r.status_code == 401, f"{method} {path} gave {r.status_code}"
    r = client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_and_roles():
    me = client.get("/api/me", headers=auth("Rey Responder")).json()
    assert me["name"] == "Rey Responder" and me["role"] == "responder"
    me = client.get("/api/me", headers=auth("admin ana")).json()  # name is not case sensitive
    assert me["role"] == "super_admin" and me["idle_timeout_minutes"] == config.STAFF_IDLE_MINUTES


def test_responder_is_blocked_from_super_admin_routes():
    h = auth("Rey Responder")
    assert client.get("/api/admin/users", headers=h).status_code == 403
    assert client.get("/api/admin/audit-log", headers=h).status_code == 403
    r = client.post("/api/admin/users", headers=h, json={"name": "Sneaky", "password": PASSWORD, "role": "super_admin"})
    assert r.status_code == 403
    assert client.post(f"/api/admin/users/{ADMIN_ID}/lock", headers=h).status_code == 403
    assert client.post(f"/api/admin/users/{ADMIN_ID}/unlock", headers=h).status_code == 403
    assert client.delete(f"/api/admin/users/{ADMIN_ID}", headers=h).status_code == 403
    db = db_session()
    try:
        assert db.query(User).filter(User.name == "Sneaky").count() == 0
        assert not db.get(User, ADMIN_ID).is_locked
    finally:
        db.close()
    # a responder still passes the responder-level check
    assert client.get("/api/me", headers=h).status_code == 200


def test_lockout_after_five_wrong_tries_and_unlock():
    uid = make_user("Lock Test", "responder")
    for i in range(config.SIGNIN_MAX_WRONG_TRIES - 1):
        r = sign_in("Lock Test", "wrong password")
        assert r.status_code == 401, (i, r.status_code)
    r = sign_in("Lock Test", "wrong password")  # the 5th wrong try locks it
    assert r.status_code == 423 and "locked" in r.json()["detail"].lower()
    # even the right password is refused while locked
    r = sign_in("Lock Test", PASSWORD)
    assert r.status_code == 423

    # a Super admin sees it as locked, then unlocks it
    admin = auth("Admin Ana")
    listed = {u["id"]: u for u in client.get("/api/admin/users", headers=admin).json()}
    assert listed[uid]["status"] == "locked_for_wrong_tries"
    r = client.post(f"/api/admin/users/{uid}/unlock", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert sign_in("Lock Test", PASSWORD).status_code == 200


def test_lock_runs_out_after_the_lock_time():
    make_user("Timed Lock", "responder")
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
    make_user("Reset Test", "responder")
    for _ in range(config.SIGNIN_MAX_WRONG_TRIES - 1):
        assert sign_in("Reset Test", "bad bad bad").status_code == 401
    assert sign_in("Reset Test", PASSWORD).status_code == 200
    for _ in range(config.SIGNIN_MAX_WRONG_TRIES - 1):  # not locked: the count started again
        assert sign_in("Reset Test", "bad bad bad").status_code == 401
    assert sign_in("Reset Test", PASSWORD).status_code == 200


def test_unknown_name_and_wrong_password_look_the_same():
    a = sign_in("Nobody Here", PASSWORD)
    b = sign_in("Rey Responder", "wrong password")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_idle_timeout():
    make_user("Idle Test", "responder")
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
    make_user("Out Test", "responder")
    h = auth("Out Test")
    assert client.post("/api/auth/sign-out", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/auth/sign-out", headers=h).status_code == 200  # twice is fine
    assert client.post("/api/auth/sign-out").status_code == 200  # no token is fine too


def test_super_admin_creates_locks_unlocks_removes():
    admin = auth("Admin Ana")
    r = client.post("/api/admin/users", headers=admin, json={"name": "New Person", "password": PASSWORD, "role": "responder"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert "password" not in r.text and "hash" not in r.text
    dup = client.post("/api/admin/users", headers=admin, json={"name": "new  PERSON", "password": PASSWORD, "role": "responder"})
    assert dup.status_code == 409
    short = client.post("/api/admin/users", headers=admin, json={"name": "Short Pw", "password": "abc", "role": "responder"})
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
    token = sign_in("Rey Responder").json()["token"]
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
        user = db.query(User).filter(User.name == "Rey Responder").one()
        audit.record(db, user, "report.resolve", target="report:12", detail={"note": "Team sent"})
        db.commit()
    finally:
        db.close()
    entry = client.get("/api/admin/audit-log?action=report.resolve", headers=auth("Admin Ana")).json()[0]
    assert entry["actor_name"] == "Rey Responder" and entry["actor_role"] == "responder"
    assert entry["target"] == "report:12" and entry["detail"] == {"note": "Team sent"}


def test_first_super_admin_setup_refuses_a_second():
    db = db_session()
    try:
        try:
            accounts.create_first_super_admin(db, "Another Admin", PASSWORD)
        except accounts.AccountError as e:
            assert e.status_code == 409
        else:
            raise AssertionError("a second first-Super-admin was allowed")
    finally:
        db.close()


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
