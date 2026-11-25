"""
Two-origin hardening checks: CORS and the handling of the Admin token.

SILONG runs as two frontends (user site :5173, admin console :5174) and one backend (:8000). The admin
token must reach only the backend, and only the backend may answer a browser from one of the two sites.

Run from the backend folder (needs `pip install -r requirements-dev.txt` once):

    py tests/test_security.py

It uses its own temporary database, so typhoon.db is never touched. The public leak sweep is in
test_public_leaks.py; the 401 / 403 sweep over every admin route is in test_accounts.py.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

# Must be set BEFORE the app is imported: own database, no limits in the way, and the DEFAULT CORS list
# (an empty value counts as "not set" and also keeps a developer's backend/.env out of this test).
_tmp = tempfile.mkdtemp(prefix="silong-test-")
BACKEND = Path(__file__).resolve().parent.parent
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "1000"
os.environ["CORS_ORIGINS"] = ""
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, config  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, AuthSession, User  # noqa: E402
from app.security import hash_token  # noqa: E402
import route_helpers  # noqa: E402  (tests/route_helpers.py)

client = TestClient(app)
PASSWORD = "correct horse 1"
NEW_PASSWORD = "another horse 2"
ALLOWED = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]


def db_session():
    return SessionLocal()


def make_user(name):
    db = db_session()
    try:
        return accounts.create_user(db, name, PASSWORD, actor="test setup").id
    finally:
        db.close()


def sign_in(name, password=PASSWORD):
    return client.post("/api/auth/sign-in", json={"name": name, "password": password})


def token_of(name):
    r = sign_in(name)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def session_rows(token):
    db = db_session()
    try:
        return db.query(AuthSession).filter(AuthSession.token_hash == hash_token(token)).count()
    finally:
        db.close()


def age_sessions(name, minutes):
    db = db_session()
    try:
        uid = db.query(User).filter(User.name == name).one().id
        for s in db.query(AuthSession).filter(AuthSession.user_id == uid).all():
            s.last_used_at = s.last_used_at - timedelta(minutes=minutes)
        db.commit()
    finally:
        db.close()


ADMIN_A = make_user("Sec Admin A")
ADMIN_B = make_user("Sec Admin B")


# ------------------------------------------------------------------ CORS

def preflight(origin, method="GET", headers="authorization, x-phone-id, content-type", path="/api/me"):
    return client.options(path, headers={
        "Origin": origin, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": headers,
    })


def test_cors_defaults_are_the_two_frontends_and_not_any_website():
    assert config.CORS_ORIGINS == list(config.DEFAULT_CORS_ORIGINS) == ALLOWED
    assert "*" not in config.CORS_ORIGINS


def test_an_allowed_origin_gets_the_cors_headers():
    for origin in ALLOWED:
        r = client.get("/api/health", headers={"Origin": origin})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == origin, origin  # the origin itself, never "*"
        assert "origin" in r.headers.get("vary", "").lower()  # a cache must not hand this answer to another site
        assert "access-control-allow-credentials" not in r.headers  # the token is a header, there are no cookies


def test_a_different_origin_gets_no_cors_headers():
    for origin in ["https://evil.example", "http://localhost:5175", "http://localhost", "https://localhost:5173",
                   "http://localhost:5173.evil.example", "http://evil.example:5174", "null"]:
        r = client.get("/api/health", headers={"Origin": origin})
        assert r.status_code == 200  # the request itself is not blocked (that is the browser's job)...
        assert "access-control-allow-origin" not in r.headers, origin  # ...but it may not read the answer
    r = client.get("/api/health")  # no Origin header (curl, the tests): no CORS headers at all
    assert "access-control-allow-origin" not in r.headers


def test_a_preflight_with_authorization_and_phone_id_passes_for_an_allowed_origin():
    for origin in ALLOWED:
        r = preflight(origin)
        assert r.status_code == 200, (origin, r.status_code, r.text)
        assert r.headers["access-control-allow-origin"] == origin
        allowed = {h.strip().lower() for h in r.headers["access-control-allow-headers"].split(",")}
        assert {"authorization", "x-phone-id", "content-type"} <= allowed, allowed
    # every method the two sites use, including the ones a simple request cannot make
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        r = preflight("http://localhost:5174", method=method, path="/api/admin/users/1")
        assert r.status_code == 200 and method in r.headers["access-control-allow-methods"], (method, r.text)


def test_a_preflight_from_another_origin_or_for_another_header_fails():
    r = preflight("https://evil.example")
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
    # a header nobody uses: the preflight is refused (a browser stops on any status that is not 2xx)
    r = preflight("http://localhost:5173", headers="authorization, x-admin-debug")
    assert r.status_code == 400
    r = preflight("http://localhost:5173", method="TRACE")
    assert r.status_code == 400


def test_x_total_count_is_still_readable_by_the_admin_console():
    token = token_of("Sec Admin A")
    r = client.get("/api/admin/audit-log", headers={**bearer(token), "Origin": "http://localhost:5174"})
    assert r.status_code == 200 and "x-total-count" in r.headers, r.headers
    assert "x-total-count" in r.headers["access-control-expose-headers"].lower()


def test_cors_origins_setting_is_parsed_like_the_other_settings():
    parse = config.parse_cors_origins
    assert parse(None) == parse("") == parse("  ,  , ") == list(config.DEFAULT_CORS_ORIGINS)
    assert parse("https://admin.example.org") == ["https://admin.example.org"]
    assert parse(" https://A.example.org/ , http://localhost:5174,,http://localhost:5174 ") == ["https://a.example.org", "http://localhost:5174"]
    assert parse("*") == ["*"]  # allowed, but only because it was written down
    # it comes from backend/.env through the same loader as every other setting
    env_file = Path(_tmp) / "cors.env"
    env_file.write_text("CORS_ORIGINS=https://console.example.org,https://site.example.org\n", encoding="utf-8")
    environ = {}
    assert config.load_env_file(env_file, environ) == 1
    assert parse(environ.get("CORS_ORIGINS")) == ["https://console.example.org", "https://site.example.org"]
    environ = {"CORS_ORIGINS": "http://localhost:5174"}  # the real environment wins over the file
    config.load_env_file(env_file, environ)
    assert parse(environ["CORS_ORIGINS"]) == ["http://localhost:5174"]


def _origins_seen_by_a_fresh_app(cors_value, origins):
    """Starts a separate Python process (the middleware is built when main.py loads) and asks which origins it answers."""
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(BACKEND)!r})\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "c = TestClient(app)\n"
        f"print(json.dumps({{o: c.get('/api/health', headers={{'Origin': o}}).headers.get('access-control-allow-origin') for o in {origins!r}}}))\n"
    )
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{Path(tempfile.mkdtemp(prefix='silong-cors-')) / 'cors.db'}", "CORS_ORIGINS": cors_value}
    done = subprocess.run([sys.executable, "-W", "ignore", "-c", code], env=env, capture_output=True, text=True, cwd=str(BACKEND))
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1]), done.stderr


def test_the_setting_reaches_the_middleware_and_star_needs_to_be_written_down():
    asked = ["https://admin.example.org", "http://localhost:5174", "https://evil.example"]
    seen, _ = _origins_seen_by_a_fresh_app("https://admin.example.org", asked)
    assert seen == {"https://admin.example.org": "https://admin.example.org", "http://localhost:5174": None, "https://evil.example": None}, seen
    seen, warned = _origins_seen_by_a_fresh_app("*", asked)
    assert set(seen.values()) == {"*"}, seen
    assert "CORS_ORIGINS contains '*'" in warned  # said in the log, once, at start
    seen, warned = _origins_seen_by_a_fresh_app("", asked)  # empty = default list, not "any"
    assert seen == {"https://admin.example.org": None, "http://localhost:5174": "http://localhost:5174", "https://evil.example": None}, seen
    assert "CORS_ORIGINS contains" not in warned


# ------------------------------------------------------------------ the Admin token

def test_the_token_is_only_read_from_the_authorization_header():
    """In a query, a cookie or another header it counts for nothing on every admin route."""
    token = token_of("Sec Admin A")
    assert client.get("/api/me", headers=bearer(token)).status_code == 200  # the one place that works
    for method, path, _ in [(m, p, r) for m, p, r in route_helpers.all_routes(app) if route_helpers.kind_of(r) == "admin"]:
        url = route_helpers.fill(path)
        for extra in ({"params": {"token": token}}, {"params": {"access_token": token}},
                      {"params": {"authorization": f"Bearer {token}"}}, {"headers": {"Cookie": f"token={token}; access_token={token}"}},
                      {"headers": {"X-Auth-Token": token, "X-Token": token}}):
            r = client.request(method, url, **extra)
            assert r.status_code == 401, f"{method} {path} accepted a token outside Authorization: {extra}"
    # a token in the query next to a good header changes nothing, and a wrong header wins over a good query token
    assert client.get("/api/me", headers=bearer(token), params={"token": "other"}).status_code == 200
    assert client.get("/api/me", headers=bearer("wrong"), params={"token": token}).status_code == 401


def test_no_route_takes_a_token_as_a_parameter():
    """The route table itself: no path or query parameter of any route is called token (so a token cannot end up in a URL by design)."""
    spec = app.openapi()
    for path, ops in spec["paths"].items():
        assert "token" not in path.lower(), path
        for method, op in ops.items():
            for param in op.get("parameters", []):
                if param["in"] in ("query", "path"):
                    assert "token" not in param["name"].lower() and param["name"].lower() != "authorization", (method, path, param["name"])


def test_the_token_is_never_in_the_audit_log_or_the_server_log():
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    catch = Catch(level=logging.DEBUG)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(catch)
    root.setLevel(logging.DEBUG)
    try:
        name = "Sec Logger"
        make_user(name)
        token = token_of(name)  # sign-in
        second = token_of(name)
        client.get("/api/me", headers=bearer(token))
        client.get("/api/admin/audit-log", headers=bearer(token))
        client.get("/api/admin/reports", headers=bearer("not-a-real-token-xyz"))  # a wrong token
        client.post("/api/auth/change-password", headers=bearer(token), json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        client.post("/api/auth/sign-out", headers=bearer(token))
        client.post("/api/auth/sign-out", headers=bearer(second))
        client.get("/api/me", headers=bearer(second))  # a dead one
    finally:
        root.removeHandler(catch)
        root.setLevel(old_level)

    secrets = [token, second, hash_token(token), hash_token(second), "not-a-real-token-xyz"]
    db = db_session()
    try:
        rows = db.query(AuditLog).all()
        assert any(a.actor_name == name for a in rows)  # the actions above were audited, with the name
        for a in rows:
            blob = " ".join(str(v) for v in (a.actor_name, a.actor_role, a.action, a.target, a.detail, a.ip_hash))
            for secret in secrets:
                assert secret not in blob, f"{secret[:6]}... found in audit entry {a.action}"
    finally:
        db.close()
    # and not in what the audit log API hands to the console
    shown = client.get("/api/admin/audit-log?limit=200", headers=bearer(token_of("Sec Admin A"))).text
    for secret in secrets:
        assert secret not in shown
    for line in records:
        for secret in secrets:
            assert secret not in line, "a token reached the server log"
    # an error answer does not echo the token back either
    bad = client.get("/api/me", headers=bearer("not-a-real-token-xyz"))
    assert bad.status_code == 401 and "not-a-real-token-xyz" not in bad.text


def test_only_the_hash_of_a_token_is_stored_and_it_is_not_answered_back():
    token = token_of("Sec Admin B")
    db = db_session()
    try:
        stored = [s.token_hash for s in db.query(AuthSession).all()]
    finally:
        db.close()
    assert token not in stored and hash_token(token) in stored
    assert all(len(h) == 64 and all(c in "0123456789abcdef" for c in h) for h in stored)  # SHA-256 hex, not a token
    me = client.get("/api/me", headers=bearer(token)).text
    assert token not in me and hash_token(token) not in me


def test_signing_out_ends_the_session_on_the_server():
    token = token_of("Sec Admin A")
    assert session_rows(token) == 1
    assert client.post("/api/auth/sign-out", headers=bearer(token)).status_code == 200
    assert session_rows(token) == 0  # the row is gone, not just hidden
    assert client.get("/api/me", headers=bearer(token)).status_code == 401


def test_the_idle_limit_is_enforced_by_the_server_and_removes_the_session():
    token = token_of("Sec Admin B")
    limit = config.STAFF_IDLE_MINUTES
    assert limit == int(os.environ.get("STAFF_IDLE_MINUTES") or 30)  # 30 minutes unless .env says otherwise
    age_sessions("Sec Admin B", limit - 1)  # just under: still alive, and the timer starts again
    assert client.get("/api/me", headers=bearer(token)).status_code == 200
    age_sessions("Sec Admin B", limit + 1)  # just over: ended, whatever the browser thinks
    r = client.get("/api/me", headers=bearer(token))
    assert r.status_code == 401 and str(limit) in r.json()["detail"]
    assert session_rows(token) == 0
    assert client.get("/api/me", headers=bearer(token)).status_code == 401


def test_idle_sessions_are_also_dropped_by_the_cleanup_without_a_request():
    token = token_of("Sec Admin A")
    age_sessions("Sec Admin A", config.STAFF_IDLE_MINUTES + 1)
    assert session_rows(token) == 1  # nobody asked yet
    db = db_session()
    try:
        assert accounts.purge_idle_sessions(db) >= 1
    finally:
        db.close()
    assert session_rows(token) == 0 and client.get("/api/me", headers=bearer(token)).status_code == 401


def test_lock_remove_and_password_reset_end_every_old_token_on_the_server():
    boss = token_of("Sec Admin A")
    cases = {}
    for what in ("lock", "remove", "reset"):
        name = f"Sec Victim {what}"
        uid = make_user(name)
        cases[what] = (uid, name, [token_of(name), token_of(name)])  # two browsers
    for _, _, tokens in cases.values():
        for t in tokens:
            assert client.get("/api/me", headers=bearer(t)).status_code == 200
    assert client.post(f"/api/admin/users/{cases['lock'][0]}/lock", headers=bearer(boss)).status_code == 200
    assert client.delete(f"/api/admin/users/{cases['remove'][0]}", headers=bearer(boss)).status_code == 200
    r = client.post(f"/api/admin/users/{cases['reset'][0]}/reset-password", headers=bearer(boss), json={"new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text
    for what, (_, name, tokens) in cases.items():
        for t in tokens:
            assert session_rows(t) == 0, f"{what}: the session is still on the server"
            for path in ("/api/me", "/api/admin/summary", "/api/admin/users"):
                assert client.get(path, headers=bearer(t)).status_code == 401, (what, path)
    assert sign_in("Sec Victim reset", PASSWORD).status_code == 401  # the old password is dead too
    assert sign_in("Sec Victim reset", NEW_PASSWORD).status_code == 200
    # the Admin who did it is untouched
    assert client.get("/api/me", headers=bearer(boss)).status_code == 200


def test_a_changed_password_ends_the_other_sessions_on_the_server_and_keeps_this_one():
    name = "Sec Changer"
    make_user(name)
    here, other = token_of(name), token_of(name)
    r = client.post("/api/auth/change-password", headers=bearer(here), json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text
    assert session_rows(here) == 1 and session_rows(other) == 0
    assert client.get("/api/me", headers=bearer(other)).status_code == 401


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
