"""
Public leak sweep: nothing private reaches a public answer.

Seeds demo data (help requests with contacts, hazards, a pending place, a removed center, an Admin who
took a report, a blocked phone, Admin-written advisories and settings), then calls EVERY public GET route
as the public would (no token, a phone ID only, a wrong token, an expired Admin token, a locked Admin's
token) and fails if an answer holds any of:
  - a contact number from a report (or from a place nobody approved),
  - a phone ID, its hash, or an IP hash,
  - the exact coordinate of a help request or hazard report,
  - an Admin's name,
  - the control-room number,
  - an audit or internal field (by name), or the text an Admin wrote for the audit log.

The public routes are taken from the route table, so a new public GET that this sweep does not know
fails the test until it is added here.

Run from the backend folder (needs `pip install -r requirements-dev.txt` once):

    py tests/test_public_leaks.py

It uses its own temporary database, so typhoon.db is never touched.
"""
import json
import math
import os
import re
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

# Must be set BEFORE the app is imported: own database, no limits in the way.
_tmp = tempfile.mkdtemp(prefix="silong-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "1000"
os.environ["REPORT_PHONE_COOLDOWN_SECONDS"] = "0"
os.environ["REPORT_PHONE_MAX"] = "1000"
os.environ["REPORT_IP_MAX"] = "1000"
os.environ["REPORT_READ_MAX"] = "1000"
os.environ["STATUS_COOLDOWN_SECONDS"] = "0"
os.environ["STATUS_IP_MAX_UPDATES"] = "1000"
os.environ["MANAGE_MAX_ACTIONS"] = "1000"
os.environ["PENDING_PLACES_PER_PHONE"] = "50"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, config, weather_service  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (ActionLog, AuditLog, AuthSession, BlockedPhone, ForgivenPhone, Report,  # noqa: E402
                        User, UserEvacuationCenter)
import route_helpers  # noqa: E402  (tests/route_helpers.py)

client = TestClient(app)
PASSWORD = "correct horse 1"


def db_session():
    return SessionLocal()


def make_user(name):
    db = db_session()
    try:
        return accounts.create_user(db, name, PASSWORD, actor="test setup").id
    finally:
        db.close()


def sign_in_token(name):
    r = client.post("/api/auth/sign-in", json={"name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


ANA, BEN, OLD, LOCKED = "Leak Admin Ana", "Leak Admin Ben", "Leak Admin Olga", "Leak Admin Lars"
for _n in (ANA, BEN, OLD, LOCKED):
    make_user(_n)
H_ANA, H_BEN = bearer(sign_in_token(ANA)), bearer(sign_in_token(BEN))

# ---------------------------------------------------------------- the demo data
# Exact spots with many decimals, so a copy of one cannot be an accident. All inside Batangas City.
HELP_SPOT = (13.74812345, 121.07123456)
HELP_SPOT_2 = (13.74399871, 121.06543219)
HELP_SPOT_3 = (13.75433219, 121.04987654)
HAZARD_SPOT = (13.75123457, 121.05234568)
HAZARD_SPOT_2 = (13.76234567, 121.07654321)
EXACT_SPOTS = [HELP_SPOT, HELP_SPOT_2, HELP_SPOT_3, HAZARD_SPOT, HAZARD_SPOT_2]

CONTACT_HELP, CONTACT_HELP_2, CONTACT_HELP_3 = "0917 555 1234", "0918 222 3344", "0922 444 5566"
CONTACT_HAZARD = "0920 888 7766"
CONTACT_PENDING, CONTACT_REMOVED = "0919 111 2299", "0921 333 4455"
CONTROL_ROOM = "043 555 0199"
SUPPORT_NUMBER, SUPPORT_EMAIL = "043 555 0100", "help@silong.example"
RESOLUTION_TEXT, FALSE_TEXT, OVERRIDE_REASON = "Resolution text only Admins read", "False-report text only Admins read", "Override reason only the audit log keeps"

PHONES = {name: f"phone-leak-{name}-0123456789abcdef" for name in
          ("sender", "sender2", "sender3", "hazard", "hazard2", "bad", "adder", "adder2", "remover", "bystander", "status")}


def send(phone, kind, where, **extra):
    body = {"kind": kind, "category": "Trapped" if kind == "help" else "Flooded road",
            "latitude": where[0], "longitude": where[1], **extra}
    r = client.post("/api/reports", headers={"X-Phone-Id": phone}, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def add_place(phone, name, where, **extra):
    r = client.post("/api/evacuation-centers", headers={"X-Phone-Id": phone},
                    json={"name": name, "center_type": "permanent", "max_capacity": 100,
                          "latitude": where[0], "longitude": where[1], **extra})
    assert r.status_code == 201, r.text
    return r.json()


def seed():
    ids = {}
    # a help request an Admin took, one that was resolved, one marked false
    ids["help_taken"] = send(PHONES["sender"], "help", HELP_SPOT, contact=CONTACT_HELP, people=3, can_move="no", note="Roof, water rising")["id"]
    assert client.post(f"/api/admin/reports/{ids['help_taken']}/take", headers=H_ANA).status_code == 200
    ids["help_resolved"] = send(PHONES["sender2"], "help", HELP_SPOT_2, contact=CONTACT_HELP_2)["id"]
    assert client.post(f"/api/admin/reports/{ids['help_resolved']}/resolve", headers=H_BEN, json={"what_was_done": RESOLUTION_TEXT}).status_code == 200
    ids["help_false"] = send(PHONES["sender3"], "help", HELP_SPOT_3, contact=CONTACT_HELP_3)["id"]
    assert client.post(f"/api/admin/reports/{ids['help_false']}/mark-false", headers=H_BEN, json={"reason": FALSE_TEXT}).status_code == 200
    # hazards: two phones about the same spot, one with a contact, verified by an Admin; another on its own
    ids["hazard"] = send(PHONES["hazard"], "hazard", HAZARD_SPOT, contact=CONTACT_HAZARD, note="Knee-deep water")["id"]
    send(PHONES["hazard2"], "hazard", (HAZARD_SPOT[0] + 0.00001, HAZARD_SPOT[1] + 0.00001))
    assert client.post(f"/api/admin/reports/{ids['hazard']}/verify", headers=H_ANA).status_code == 200
    ids["hazard_2"] = send(PHONES["hazard"], "hazard", HAZARD_SPOT_2)["id"]
    # a blocked phone: three reports, all marked false
    bad = [send(PHONES["bad"], "help", (13.7000 + i * 0.01, 121.0000 + i * 0.01), contact=f"0933 000 000{i}")["id"] for i in range(3)]
    for rid in bad:
        assert client.post(f"/api/admin/reports/{rid}/mark-false", headers=H_BEN, json={"reason": FALSE_TEXT}).status_code == 200
    # places: pending (nobody approved), approved (public), removed (an Admin took it away)
    ids["pending"] = add_place(PHONES["adder"], "Leak Pending Gym", (13.6325, 121.0125), contact=CONTACT_PENDING, address="Pending street")["id"]
    ids["approved"] = add_place(PHONES["adder2"], "Leak Approved Hall", (13.6450, 121.0250), contact="0944 000 1111")["id"]
    assert client.post(f"/api/admin/places/{ids['approved']}/approve", headers=H_BEN).status_code == 200
    ids["removed"] = add_place(PHONES["remover"], "Leak Removed Hall", (13.6575, 121.0375), contact=CONTACT_REMOVED)["id"]
    assert client.post(f"/api/admin/places/{ids['removed']}/approve", headers=H_BEN).status_code == 200
    assert client.delete(f"/api/evacuation-centers/{ids['removed']}", headers=H_ANA).status_code == 200
    # Admin-written public content and settings, so an Admin's name is stored next to what the public reads
    r = client.post("/api/admin/advisories", headers=H_BEN, json={
        "title": "Leak check advisory", "details": "Stay indoors.", "organization": "PAGASA",
        "source_url": "https://www.pagasa.dost.gov.ph/bulletin/leak"})
    assert r.status_code == 201, r.text
    r = client.post("/api/admin/emergency-numbers", headers=H_BEN, json={"number": "8888", "name": "Leak check line"})
    assert r.status_code == 201, r.text
    r = client.patch("/api/admin/contact-settings", headers=H_BEN, json={
        "control_room_number": CONTROL_ROOM, "support_number": SUPPORT_NUMBER, "support_email": SUPPORT_EMAIL})
    assert r.status_code == 200, r.text
    # an Admin's status for a public place (their name is stored on the row) and a normal user's
    r = client.post(f"/api/admin/facilities/{ids['approved']}/status-override", headers=H_BEN,
                    json={"status": "almost_full", "note": "Counted at the gate", "reason": OVERRIDE_REASON})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/facilities/{ids['approved']}/status", headers={"X-Phone-Id": PHONES["status"]}, json={"status": "open"})
    assert r.status_code == 201, r.text
    # sessions that must count as nobody: an expired one and one of a locked account
    ids["expired_token"] = sign_in_token(OLD)
    db = db_session()
    try:
        for s in db.query(AuthSession).filter(AuthSession.user_id == db.query(User).filter(User.name == OLD).one().id):
            s.last_used_at = s.last_used_at - timedelta(minutes=config.STAFF_IDLE_MINUTES + 5)
        db.commit()
    finally:
        db.close()
    ids["locked_token"] = sign_in_token(LOCKED)
    lock_id = None
    db = db_session()
    try:
        lock_id = db.query(User).filter(User.name == LOCKED).one().id
    finally:
        db.close()
    assert client.post(f"/api/admin/users/{lock_id}/lock", headers=H_ANA).status_code == 200
    # a static (built-in) facility to ask about
    ids["static"] = next(f["id"] for f in client.get("/api/facilities").json() if not f["key"].startswith("user:"))
    return ids


IDS = seed()

# ---------------------------------------------------------------- what must never show up
FORBIDDEN_KEYS = {
    "phone_hash", "ip_hash", "phone_id", "password_hash", "token_hash", "name_key", "actor_id", "actor_name", "actor_role",
    "taken_by", "taken_at", "closed_by", "closed_at", "resolution_note", "false_reason", "verified_by", "verified_at",
    "reviewed_by", "reviewed_at", "removed_by", "changed_by", "created_by", "updated_by", "reject_reason",
    "control_room_number", "false_reports", "blocked_at", "failed_attempts", "locked_until", "is_locked", "group_id", "audit",
}


def _secrets():
    """Everything private in the database, read from the tables themselves so nothing is typed in twice."""
    db = db_session()
    try:
        names = {u.name for u in db.query(User).all()}
        contacts = {r.contact for r in db.query(Report).all() if r.contact}
        # the contact of a place is public once an Admin approved it; before that and after a removal it is private
        pending_or_removed = {c.contact for c in db.query(UserEvacuationCenter).all() if c.contact and c.id in (IDS["pending"], IDS["removed"])}
        hashes = {r.phone_hash for r in db.query(Report).all()} | {r.ip_hash for r in db.query(Report).all()}
        hashes |= {b.phone_hash for b in db.query(BlockedPhone).all()} | {f.phone_hash for f in db.query(ForgivenPhone).all()}
        hashes |= {c.phone_hash for c in db.query(UserEvacuationCenter).all() if c.phone_hash}
        hashes |= {a.ip_hash for a in db.query(ActionLog).all()} | {a.ip_hash for a in db.query(AuditLog).all() if a.ip_hash}
        hashes = {h for h in hashes if h}
        audit_texts = {a.detail for a in db.query(AuditLog).all() if a.detail}
        assert db.query(BlockedPhone).count() == 1  # the demo data really blocked a phone
        assert any(r.status == "being_handled" and r.taken_by == ANA for r in db.query(Report).all())  # and an Admin took a report
    finally:
        db.close()
    return {
        "names": names,
        "contacts": contacts | pending_or_removed,
        "pending_contact": CONTACT_PENDING,
        "hashes": hashes,
        "phones": set(PHONES.values()),
        "control_room": {CONTROL_ROOM},
        "admin_texts": {RESOLUTION_TEXT, FALSE_TEXT, OVERRIDE_REASON},
        "audit_texts": audit_texts,
    }


SECRETS = _secrets()
assert len(SECRETS["hashes"]) >= 5 and ANA in SECRETS["names"] and CONTACT_HELP in SECRETS["contacts"]


def _digits(text):
    return re.sub(r"\D", "", text)


def _numbers(node):
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield float(node)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _numbers(v)
    elif isinstance(node, list):
        for v in node:
            yield from _numbers(v)


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def problems(where, response, *, own_contacts=()):
    """What is private in this answer. `own_contacts`: numbers that the caller itself sent and may see back."""
    text = response.text
    low = text.lower()
    digits = _digits(text)
    found = []
    try:
        body = response.json()
    except ValueError:
        body = None
    for name in SECRETS["names"]:
        if name.lower() in low:
            found.append(f"an Admin's name ({name})")
    for number in SECRETS["contacts"] - set(own_contacts):
        if number in text or _digits(number) in digits:
            found.append(f"a contact number ({number})")
    for number in SECRETS["control_room"]:
        if number in text or _digits(number) in digits:
            found.append("the control-room number")
    for h in SECRETS["hashes"]:
        if h in text or (len(h) >= 8 and h[:8] in text):
            found.append(f"a phone or IP hash ({h[:8]})")
    for phone in SECRETS["phones"]:
        if phone in text:
            found.append(f"a phone ID ({phone})")
    for t in SECRETS["admin_texts"] | SECRETS["audit_texts"]:
        if t and t in text:
            found.append(f"text meant for Admins or the audit log ({t[:30]})")
    for lat, lon in EXACT_SPOTS:
        for value in (lat, lon):
            if f"{value:.8f}"[:10] in text:  # 13.7481234 / 121.071234: the first decimals that make it exact
                found.append(f"an exact coordinate ({value})")
    if body is not None:
        exact = [c for spot in EXACT_SPOTS for c in spot]
        if any(math.isclose(n, c, abs_tol=1e-7) for n in _numbers(body) for c in exact):
            found.append("an exact coordinate (as a number)")
        leaked_keys = sorted(set(_keys(body)) & FORBIDDEN_KEYS)
        if leaked_keys:
            found.append(f"internal fields {leaked_keys}")
    return [f"{where}: {f}" for f in sorted(set(found))]


# ---------------------------------------------------------------- the sweep
def sample_reply():
    """What Open-Meteo sends (the parts we read), so /api/weather answers without the network."""
    return {
        "current": {"time": "2026-11-16T15:00", "temperature_2m": 28.4, "relative_humidity_2m": 84, "apparent_temperature": 33.1,
                    "precipitation": 1.2, "weather_code": 61, "wind_speed_10m": 22.5, "wind_gusts_10m": 41.0, "is_day": 1},
        "daily": {"time": ["2026-11-16", "2026-11-17", "2026-11-18"], "weather_code": [61, 80, 3],
                  "temperature_2m_max": [31.0, 30.2, 31.5], "temperature_2m_min": [25.1, 24.8, 25.0],
                  "precipitation_sum": [8.4, 3.1, 0.0], "precipitation_probability_max": [80, 60, 20],
                  "wind_speed_10m_max": [30.1, 25.0, 18.2]},
    }


def who():
    """The callers a public route must treat alike: [(label, headers)]."""
    return [
        ("no token", {}),
        ("a phone ID", {"X-Phone-Id": PHONES["bystander"]}),
        ("a wrong token", {**bearer("not-a-real-token"), "X-Phone-Id": PHONES["bystander"]}),
        ("an expired Admin token", bearer(IDS["expired_token"])),
        ("a locked Admin's token", bearer(IDS["locked_token"])),
        ("a token in the wrong form", {"Authorization": "Token abc"}),
    ]


def variants(path):
    """Query strings and path values to call a public GET with, aimed at the demo data. Unknown route: None."""
    if path == "/api/hazards/nearby":
        return [{"params": {"latitude": lat, "longitude": lon}} for lat, lon in EXACT_SPOTS]
    if path == "/api/advisories":
        return [{}, {"params": {"official": "true"}}, {"params": {"limit": 100}}]
    if path == "/api/emergency-numbers":
        return [{}] + [{"params": {"category": c}} for c in config.EMERGENCY_CATEGORIES]
    if path == "/api/facilities/{facility_id}/status/history":
        return [{"path": route_helpers.fill(path, str(IDS[k])), "params": {"limit": 100}} for k in ("static", "approved", "pending", "removed")]
    if path in ("/api/facilities", "/api/reports/mine", "/api/support-contact", "/api/weather", "/api/health"):
        return [{}]
    return None


def public_gets():
    return [(p, r) for m, p, r in route_helpers.all_routes(app) if m == "GET" and route_helpers.kind_of(r) == "public"]


def test_the_sweep_knows_every_public_get_route():
    paths = [p for p, _ in public_gets()]
    assert len(paths) >= 9, paths
    unknown = [p for p in paths if variants(p) is None]
    assert not unknown, f"a new public GET route needs a place in this leak sweep: {unknown}"


def test_no_public_get_leaks_anything_private():
    leaks, calls = [], 0
    weather_service.reset()
    with mock.patch.object(weather_service, "_http_get_json", lambda url, timeout: sample_reply()):  # no network in tests
        for path, _route in public_gets():
            for v in variants(path):
                url = v.get("path", path)
                for label, headers in who():
                    r = client.get(url, headers=headers, params=v.get("params"))
                    calls += 1
                    assert r.status_code < 500, (url, label, r.status_code, r.text)
                    assert r.status_code in (200, 400, 404), (url, label, r.status_code)  # 400: /mine without a phone ID; 404: a place the caller may not see
                    leaks += problems(f"GET {url} {v.get('params') or ''} as {label}", r)
    assert calls >= 9 * 6, calls
    assert not leaks, "\n".join(leaks)


def test_the_sweep_would_catch_a_leak():
    """The detector itself: it must fire on the things it is meant to find (otherwise a pass proves nothing)."""
    class Fake:
        def __init__(self, text):
            self.text = text

        def json(self):
            return json.loads(self.text)

    cases = [
        (json.dumps({"x": f"call {CONTACT_HELP}"}), "a contact number"),
        (json.dumps({"x": "0917-555-1234"}), "a contact number"),
        (json.dumps({"taken_by": "somebody"}), "internal fields"),
        (json.dumps({"x": ANA}), "an Admin's name"),
        (json.dumps({"latitude": HELP_SPOT[0], "longitude": 121.5}), "an exact coordinate"),
        (json.dumps({"x": f"ring {CONTROL_ROOM}"}), "the control-room number"),
        (json.dumps({"x": sorted(SECRETS["hashes"])[0]}), "a phone or IP hash"),
        (json.dumps({"x": PHONES["bad"]}), "a phone ID"),
        (json.dumps({"x": RESOLUTION_TEXT}), "text meant for Admins"),
    ]
    for text, expected in cases:
        assert any(expected in p for p in problems("probe", Fake(text))), (text, expected)
    assert problems("probe", Fake(json.dumps({"latitude": 13.7565, "longitude": 121.0583, "name": "A place"}))) == []


def test_what_the_public_is_meant_to_see_is_still_there():
    """Hiding too much would also pass the sweep: the public answers must still carry the useful parts."""
    sup = client.get("/api/support-contact").json()
    assert sup == {"support_email": SUPPORT_EMAIL, "support_number": SUPPORT_NUMBER}  # public, and not the control-room number
    assert "Leak check line" in client.get("/api/emergency-numbers").text
    assert "Leak check advisory" in client.get("/api/advisories").text
    listing = {f["id"]: f for f in client.get("/api/facilities").json()}
    assert IDS["approved"] in listing and IDS["static"] in listing
    assert IDS["pending"] not in listing and IDS["removed"] not in listing  # nobody else sees a pending or removed place
    history = client.get(f"/api/facilities/{IDS['approved']}/status/history", params={"limit": 100}).json()
    assert {"official", "user"} <= {row["source"] for row in history}  # an Admin's status shows as "official", without a name
    hazards = client.get("/api/hazards/nearby", params={"latitude": HAZARD_SPOT[0], "longitude": HAZARD_SPOT[1]}).json()
    assert hazards and hazards[0]["status"] == "verified"
    for h in hazards:  # an approximate spot, near the real one but never the real one
        assert abs(h["latitude"] - HAZARD_SPOT[0]) < 0.01 and h["latitude"] != HAZARD_SPOT[0] and h["longitude"] != HAZARD_SPOT[1]
        assert set(h) == {"id", "latitude", "longitude", "status", "label", "category"}


def test_a_sender_sees_only_a_status_never_the_contact_or_the_handler():
    """/api/reports/mine for the phone that sent them. Its own spot comes back to it (it typed it); nothing else private does."""
    rows = client.get("/api/reports/mine", headers={"X-Phone-Id": PHONES["sender"]}).json()
    assert len(rows) == 1 and rows[0]["status"] == "being_handled" and rows[0]["label"] == "Being handled"
    assert set(rows[0]) == {"id", "kind", "status", "label", "category", "latitude", "longitude", "note", "created_at", "updated_at"}
    r = client.get("/api/reports/mine", headers={"X-Phone-Id": PHONES["sender"]})
    assert [p for p in problems("mine as the sender", r) if "exact coordinate" not in p] == []  # only its own spot may come back
    assert ANA not in r.text and CONTACT_HELP not in r.text and PHONES["sender"] not in r.text
    # the closed ones: a false report reads as plain "Resolved" to its sender, with no reason
    rows = client.get("/api/reports/mine", headers={"X-Phone-Id": PHONES["sender3"]}).json()
    assert [x["status"] for x in rows] == ["resolved"]
    assert FALSE_TEXT not in json.dumps(rows) and "false" not in json.dumps([x["label"] for x in rows]).lower()
    # a blocked phone reads its own reports like anyone, and learns nothing about the block
    r = client.get("/api/reports/mine", headers={"X-Phone-Id": PHONES["bad"]})
    assert r.status_code == 200 and "block" not in r.text.lower() and "false" not in r.text.lower()
    # another phone sees none of this
    assert client.get("/api/reports/mine", headers={"X-Phone-Id": PHONES["bystander"]}).json() == []


def test_the_adder_of_a_pending_place_does_not_get_hashes_or_admin_names_back():
    """The phone that added a place may see it while it waits (its own contact comes back to it)."""
    r = client.get("/api/facilities", headers={"X-Phone-Id": PHONES["adder"]})
    listing = {f["id"]: f for f in r.json()}
    assert IDS["pending"] in listing  # visible to its own adder only
    assert problems("facilities as the adder", r, own_contacts={CONTACT_PENDING}) == []
    assert IDS["pending"] not in {f["id"] for f in client.get("/api/facilities", headers={"X-Phone-Id": PHONES["bystander"]}).json()}


def test_answers_of_public_routes_that_take_an_optional_token_treat_a_wrong_token_as_a_user():
    """POST /api/facilities/{id}/status: a user token (none), a wrong, expired or locked token is 'Reported by a user'; only a good Admin is official."""
    fid = IDS["approved"]
    shapes, tried = {}, 0
    for label, headers in who():
        r = client.post(f"/api/facilities/{fid}/status", headers=headers, json={"status": "open", "note": f"as {label}"})
        tried += 1
        assert r.status_code == 201, (label, r.status_code, r.text)
        body = r.json()
        assert body["source"] == "user" and body["source_label"] == "Reported by a user", (label, body)  # never promoted to an Admin
        assert problems(f"POST status as {label}", r) == []
        shapes[label] = set(body)
    admin = client.post(f"/api/facilities/{fid}/status", headers=H_ANA, json={"status": "almost_full", "note": "as an Admin"})
    assert admin.status_code == 201 and admin.json()["source"] == "official" and admin.json()["source_label"] == "Confirmed by official"
    assert problems("POST status as an Admin", admin) == []  # an Admin's own answer has no name either
    assert all(s == set(admin.json()) for s in shapes.values()), (shapes, set(admin.json()))  # the same shape for every caller
    assert tried == len(who())
    # and what everybody reads afterwards has no Admin name, from the history to the map list
    for path in (f"/api/facilities/{fid}/status/history", "/api/facilities"):
        assert problems(path, client.get(path, params={"limit": 100} if "history" in path else None)) == []


def test_answers_to_writes_by_the_public_have_no_hash_or_admin_name():
    r = client.post("/api/reports", headers={"X-Phone-Id": PHONES["bystander"]}, json={
        "kind": "help", "category": "Trapped", "latitude": 13.7712345, "longitude": 121.0612345, "contact": "0955 123 4567"})
    assert r.status_code == 201
    assert set(r.json()) == {"id", "kind", "status", "label", "created_at", "message"}
    assert "0955" not in r.text and PHONES["bystander"] not in r.text and "13.77123" not in r.text
    r = client.post("/api/evacuation-centers", headers={"X-Phone-Id": PHONES["bystander"]}, json={
        "name": "Leak Echo Gym", "center_type": "permanent", "max_capacity": 50, "latitude": 13.6700, "longitude": 121.0500})
    assert r.status_code == 201
    assert problems("POST evacuation-centers", r) == []
    # a blocked phone's refusal says nothing about why
    r = client.post("/api/reports", headers={"X-Phone-Id": PHONES["bad"]}, json={
        "kind": "help", "category": "Trapped", "latitude": 13.77, "longitude": 121.06, "contact": "0966 000 1111"})
    assert r.status_code == 403 and problems("blocked phone refusal", r) == []


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
