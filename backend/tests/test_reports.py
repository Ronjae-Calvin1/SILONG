"""
Part 2 checks: help requests and hazard reports.

Run from the backend folder (needs `pip install -r requirements-dev.txt` once):

    py tests/test_reports.py

It uses its own temporary database, so typhoon.db is never touched. (pytest
also works: `py -m pytest tests/test_reports.py -q`, if you have it installed.)
"""
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

# Must be set BEFORE the app is imported: own database, no limits in the way.
_tmp = tempfile.mkdtemp(prefix="silong-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "1000"
os.environ["REPORT_PHONE_COOLDOWN_SECONDS"] = "0"
os.environ["REPORT_PHONE_MAX"] = "1000"
os.environ["REPORT_IP_MAX"] = "1000"
os.environ["REPORT_READ_MAX"] = "1000"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, config, report_service  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, BlockedPhone, Report  # noqa: E402
from app.rate_limit import read_limiter, report_limiter  # noqa: E402

client = TestClient(app)
PASSWORD = "correct horse 1"

# Two places in Batangas City, a bit more than 2 km apart.
HOME = (13.7565, 121.0583)
NEAR = (13.7610, 121.0583)  # about 500 m north of HOME
FAR = (13.7790, 121.0583)  # about 2.5 km north of HOME


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


RESP = make_user("Rey Responder", "responder")
RESP2 = make_user("Ria Responder", "responder")
ADMIN = make_user("Admin Ana", "super_admin")
H_RESP, H_RESP2, H_ADMIN = auth("Rey Responder"), auth("Ria Responder"), auth("Admin Ana")

_phones = iter(range(1, 10_000))


def new_phone():
    """A random-looking phone ID (16+ characters), different every call."""
    return f"phone-test-{next(_phones):08d}-abcdef"


def send(phone, kind, where=HOME, **extra):
    """Sends a report. A help request gets a contact and every report a category unless the test gives its own."""
    body = {"kind": kind, "category": "Trapped" if kind == "help" else "Flooded road",
            "latitude": where[0], "longitude": where[1], **extra}
    if kind == "help" and "contact" not in extra:
        body["contact"] = "0917 000 0000"
    body = {k: v for k, v in body.items() if v is not None}  # contact=None means "leave it out"
    return client.post("/api/reports", headers={"X-Phone-Id": phone}, json=body)


def nearby(where, phone=None):
    headers = {"X-Phone-Id": phone} if phone else {}
    r = client.get("/api/hazards/nearby", params={"latitude": where[0], "longitude": where[1]}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def mine(phone):
    r = client.get("/api/reports/mine", headers={"X-Phone-Id": phone})
    assert r.status_code == 200, r.text
    return r.json()


def staff_list(headers=H_RESP, **params):
    r = client.get("/api/responder/reports", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def audit_actions():
    db = db_session()
    try:
        return [(a.actor_name, a.action, a.target) for a in db.query(AuditLog).order_by(AuditLog.id).all()]
    finally:
        db.close()


def set_created_at(report_id, days_ago):
    db = db_session()
    try:
        row = db.get(Report, report_id)
        row.created_at = report_service._now() - timedelta(days=days_ago)
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- sending

def test_help_request_is_sent_and_the_sender_sees_status_only():
    phone = new_phone()
    r = send(phone, "help", contact="0917 123 4567", note="Water is rising, two kids")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "new" and r.json()["label"] == "New"
    mine_now = mine(phone)
    assert len(mine_now) == 1 and mine_now[0]["kind"] == "help" and mine_now[0]["label"] == "New"
    # The sender's own view carries no contact, no handler, no reason.
    assert not ({"contact", "contacts", "taken_by", "closed_by", "false_reason", "resolution_note"} & set(mine_now[0]))


def test_no_name_no_photo_nothing_extra_is_accepted():
    phone = new_phone()
    for extra in ({"name": "Juan"}, {"photo": "data:image/png;base64,AAAA"}, {"phone_id": phone}):
        r = send(phone, "help", **extra)
        assert r.status_code == 422, f"{extra} gave {r.status_code}"
    assert mine(phone) == []


def test_phone_id_is_required_and_checked():
    body = {"kind": "help", "category": "Trapped", "contact": "0917 000 0000", "latitude": HOME[0], "longitude": HOME[1]}
    assert client.post("/api/reports", json=body).status_code == 400
    assert client.post("/api/reports", json=body, headers={"X-Phone-Id": "short"}).status_code == 400
    assert client.post("/api/reports", json=body, headers={"X-Phone-Id": "has spaces in it, not allowed!!"}).status_code == 400
    assert client.get("/api/reports/mine").status_code == 400


def test_location_must_be_in_the_city_and_text_is_limited():
    phone = new_phone()
    assert send(phone, "help", where=(14.5995, 120.9842)).status_code == 422  # Manila
    assert send(phone, "help", note="x" * (config.REPORT_NOTE_MAX + 1)).status_code == 422
    assert send(phone, "help", contact="9" * (config.REPORT_CONTACT_MAX + 1)).status_code == 422
    assert send(phone, "teapot").status_code == 422
    assert client.post("/api/reports", headers={"X-Phone-Id": phone}, content='{"kind":"help","category":"x","contact":"1","latitude":NaN,"longitude":121}').status_code == 422
    assert mine(phone) == []


def test_phone_id_is_stored_hashed_and_ip_is_hashed():
    phone = new_phone()
    send(phone, "help", contact="0917 000 1111")
    db = db_session()
    try:
        row = db.query(Report).filter(Report.phone_hash == report_service.hash_phone_id(phone)).one()
        assert row.phone_hash != phone and phone not in row.phone_hash
        assert row.ip_hash and "testclient" not in row.ip_hash
        # The hash is stable (same ID, same hash), so "my reports" survives a restart.
        assert report_service.hash_phone_id(phone) == row.phone_hash
    finally:
        db.close()


# --------------------------------------------------------------------------- help is never public

def test_help_request_is_invisible_to_the_public():
    phone, other = new_phone(), new_phone()
    secret_contact, secret_note = "0999 SECRET 777", "SECRETNOTE basement"
    r = send(phone, "help", contact=secret_contact, note=secret_note)
    assert r.status_code == 201

    # Not in the nearby hazards, at the spot or anywhere else, with or without a phone ID.
    for where in (HOME, NEAR, FAR):
        assert nearby(where) == [] and nearby(where, other) == []
    # Not in another phone's own reports.
    assert mine(other) == []
    # Not in anything else the public can read.
    public = [
        client.get("/api/facilities").text,
        client.get("/api/evacuation-centers/removed").text,
        json.dumps(nearby(HOME)),
        json.dumps(mine(other)),
    ]
    for text in public:
        assert secret_contact not in text and secret_note not in text
    # And the responder list is closed to the public.
    assert client.get("/api/responder/reports").status_code == 401
    # The responders do see it, with the exact location and the contact.
    items = [i for i in staff_list()["items"] if secret_contact in i["contacts"]]
    assert len(items) == 1 and items[0]["kind"] == "help"
    assert items[0]["latitude"] == HOME[0] and items[0]["longitude"] == HOME[1]


# --------------------------------------------------------------------------- hazards

def _clean_slate_hazards():
    """Close every open hazard so each hazard check starts with no hazards around."""
    for item in staff_list(kind="hazard")["items"]:
        client.post(f"/api/responder/reports/{item['id']}/resolve", headers=H_RESP, json={"what_was_done": "test clean-up"})
    assert nearby(HOME) == []


def test_hazard_is_hidden_beyond_one_km_and_shows_only_an_approximate_spot():
    _clean_slate_hazards()
    phones = [new_phone() for _ in range(3)]
    for p in phones:
        assert send(p, "hazard", where=HOME, note="Fallen tree HIDDENDETAIL", contact="0917 HIDDENCONTACT").status_code == 201
    assert config.NEAR_ME_KM == 1

    close = nearby(NEAR)  # about 500 m away
    assert len(close) == 1
    spot = close[0]
    assert set(spot) == {"id", "latitude", "longitude", "status", "label", "category"}  # category is the only detail
    assert spot["category"] == "Flooded road"
    assert spot["status"] == "unconfirmed"
    # Approximate: not the exact point, but still close to it.
    assert (spot["latitude"], spot["longitude"]) != HOME
    assert abs(spot["latitude"] - HOME[0]) < 0.003 and abs(spot["longitude"] - HOME[1]) < 0.003
    assert "HIDDENDETAIL" not in json.dumps(close) and "HIDDENCONTACT" not in json.dumps(close)
    # Asking again gives the same spot (the error cannot be averaged away).
    assert nearby(NEAR) == close

    assert nearby(FAR) == []  # about 2.5 km away: hidden
    # The range is a setting.
    old = config.NEAR_ME_KM
    config.NEAR_ME_KM = 3
    try:
        assert len(nearby(FAR)) == 1
    finally:
        config.NEAR_ME_KM = old
    assert nearby(FAR) == []


def test_unconfirmed_needs_three_different_phones_not_three_reports_from_one():
    _clean_slate_hazards()
    a, b, c = new_phone(), new_phone(), new_phone()

    # One phone sends the same hazard three times: still one phone, nothing public.
    first = send(a, "hazard")
    assert first.status_code == 201
    for _ in range(2):
        again = send(a, "hazard")
        assert again.status_code == 200 and again.json()["id"] == first.json()["id"]  # same report, not a new one
    assert nearby(HOME) == []
    item = staff_list(kind="hazard")["items"][0]
    assert item["phones"] == 1 and item["report_count"] == 1 and item["hazard_state"] == "pending"

    # A second different phone: still hidden.
    assert send(b, "hazard", where=(HOME[0] + 0.0003, HOME[1])).status_code == 201  # ~33 m away: same hazard
    assert nearby(HOME) == []
    assert staff_list(kind="hazard")["items"][0]["phones"] == 2

    # The third different phone: Unconfirmed.
    assert send(c, "hazard").status_code == 201
    spots = nearby(HOME)
    assert len(spots) == 1 and spots[0]["status"] == "unconfirmed" and spots[0]["label"] == "Unconfirmed"
    items = staff_list(kind="hazard")["items"]
    assert len(items) == 1 and items[0]["phones"] == 3 and items[0]["hazard_state"] == "unconfirmed"

    # A hazard far from the first one is a different hazard (counts separately).
    d = new_phone()
    assert send(d, "hazard", where=FAR).status_code == 201
    assert len(staff_list(kind="hazard")["items"]) == 2
    assert nearby(FAR) == []  # one phone only

    # The setting is respected.
    old = config.HAZARD_UNCONFIRMED_PHONES
    config.HAZARD_UNCONFIRMED_PHONES = 4
    try:
        assert nearby(HOME) == []
    finally:
        config.HAZARD_UNCONFIRMED_PHONES = old
    assert len(nearby(HOME)) == 1


def test_hazard_state_counts_different_phones_not_rows():
    """The rule itself, with rows the API would never create: 3 reports, 1 phone is not enough."""
    now = report_service._now()

    def row(phone, verified=False):
        return Report(kind="hazard", phone_hash=phone, ip_hash="x", latitude=HOME[0], longitude=HOME[1],
                      status="new", created_at=now, updated_at=now, verified_at=now if verified else None)

    assert report_service.hazard_state([row("a"), row("a"), row("a")]) == "pending"
    assert report_service.hazard_state([row("a"), row("a"), row("b")]) == "pending"
    assert report_service.hazard_state([row("a"), row("b"), row("c")]) == "unconfirmed"
    assert report_service.hazard_state([row("a")] + [row("b", verified=True)]) == "verified"
    assert report_service.hazard_state([row("a", verified=True)]) == "verified"


def test_a_responder_verifies_a_hazard_and_the_public_sees_verified():
    _clean_slate_hazards()
    phone = new_phone()
    assert send(phone, "hazard").status_code == 201
    assert nearby(HOME) == []  # one phone, not verified: hidden
    item = staff_list(kind="hazard")["items"][0]

    r = client.post(f"/api/responder/reports/{item['id']}/verify", headers=H_RESP)
    assert r.status_code == 200 and r.json()["verified"] and r.json()["hazard_state"] == "verified"
    assert r.json()["verified_by"] == "Rey Responder"

    spots = nearby(HOME)
    assert len(spots) == 1 and spots[0]["status"] == "verified" and spots[0]["label"] == "Verified"
    # A second tap changes nothing and adds no second audit entry.
    before = audit_actions().count(("Rey Responder", "report.verify", f"report:{item['id']}"))
    assert client.post(f"/api/responder/reports/{item['id']}/verify", headers=H_RESP).status_code == 200
    assert audit_actions().count(("Rey Responder", "report.verify", f"report:{item['id']}")) == before == 1
    # A later report joins the verified hazard and stays verified.
    assert send(new_phone(), "hazard").status_code == 201
    assert staff_list(kind="hazard")["items"][0]["report_count"] == 2
    assert nearby(HOME)[0]["status"] == "verified"
    # A Super admin can verify too (checked on a fresh hazard).
    far_phone = new_phone()
    send(far_phone, "hazard", where=FAR)
    far_item = next(i for i in staff_list(kind="hazard")["items"] if i["latitude"] == FAR[0])
    assert client.post(f"/api/responder/reports/{far_item['id']}/verify", headers=H_ADMIN).status_code == 200
    assert nearby(FAR)[0]["status"] == "verified"


def test_only_hazards_can_be_verified():
    phone = new_phone()
    rid = send(phone, "help").json()["id"]
    assert client.post(f"/api/responder/reports/{rid}/verify", headers=H_RESP).status_code == 422


def test_a_resolved_hazard_leaves_the_public_view_and_a_new_report_starts_a_new_one():
    _clean_slate_hazards()
    phones = [new_phone() for _ in range(3)]
    for p in phones:
        send(p, "hazard")
    assert len(nearby(HOME)) == 1
    item = staff_list(kind="hazard")["items"][0]
    r = client.post(f"/api/responder/reports/{item['id']}/resolve", headers=H_RESP, json={"what_was_done": "Tree cleared"})
    assert r.status_code == 200
    assert nearby(HOME) == []
    # The same phone can report it again later: it is a new hazard, not the closed one.
    again = send(phones[0], "hazard")
    assert again.status_code == 201 and again.json()["id"] != item["id"]
    assert nearby(HOME) == []  # one phone again


# --------------------------------------------------------------------------- responder actions

def test_take_resolve_and_the_sender_sees_the_status_change():
    phone = new_phone()
    rid = send(phone, "help", contact="0917 222 3333").json()["id"]
    assert mine(phone)[0]["label"] == "New"

    r = client.post(f"/api/responder/reports/{rid}/take", headers=H_RESP)
    assert r.status_code == 200 and r.json()["status"] == "being_handled" and r.json()["taken_by"] == "Rey Responder"
    assert mine(phone)[0]["status"] == "being_handled" and mine(phone)[0]["label"] == "Being handled"
    # Taking it twice is fine for the same person; someone else is told who has it.
    assert client.post(f"/api/responder/reports/{rid}/take", headers=H_RESP).status_code == 200
    other = client.post(f"/api/responder/reports/{rid}/take", headers=H_RESP2)
    assert other.status_code == 409 and "Rey Responder" in other.json()["detail"]

    # Resolve needs what was done.
    assert client.post(f"/api/responder/reports/{rid}/resolve", headers=H_RESP, json={}).status_code == 422
    assert client.post(f"/api/responder/reports/{rid}/resolve", headers=H_RESP, json={"what_was_done": "  "}).status_code == 422
    assert mine(phone)[0]["status"] == "being_handled"
    r = client.post(f"/api/responder/reports/{rid}/resolve", headers=H_RESP, json={"what_was_done": "Rescue team reached the family"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert r.json()["resolution_note"] == "Rescue team reached the family"
    assert mine(phone)[0]["status"] == "resolved" and mine(phone)[0]["label"] == "Resolved"
    assert "Rescue team" not in json.dumps(mine(phone))  # the sender never sees the note
    # Closed reports cannot be changed again.
    assert client.post(f"/api/responder/reports/{rid}/resolve", headers=H_RESP, json={"what_was_done": "again"}).status_code == 409
    assert client.post(f"/api/responder/reports/{rid}/take", headers=H_RESP).status_code == 409
    assert client.post("/api/responder/reports/999999/take", headers=H_RESP).status_code == 404

    names = [a for a in audit_actions() if a[2] == f"report:{rid}"]
    assert ("Rey Responder", "report.take", f"report:{rid}") in names
    assert ("Rey Responder", "report.resolve", f"report:{rid}") in names


def test_mark_false_needs_a_reason_and_the_sender_sees_resolved():
    phone = new_phone()
    rid = send(phone, "help").json()["id"]
    assert client.post(f"/api/responder/reports/{rid}/mark-false", headers=H_RESP, json={}).status_code == 422
    assert client.post(f"/api/responder/reports/{rid}/mark-false", headers=H_RESP, json={"reason": ""}).status_code == 422
    r = client.post(f"/api/responder/reports/{rid}/mark-false", headers=H_RESP, json={"reason": "Called the number, no emergency"})
    assert r.status_code == 200 and r.json()["status"] == "false" and r.json()["false_reason"] == "Called the number, no emergency"
    assert mine(phone)[0]["status"] == "resolved"  # the sender gets one of the three words, never the reason
    assert "no emergency" not in json.dumps(mine(phone))
    assert ("Rey Responder", "report.mark_false", f"report:{rid}") in audit_actions()


def test_false_reports_block_a_phone_after_three():
    bad, good = new_phone(), new_phone()
    ids = []
    for _ in range(3):
        r = send(bad, "help")
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    # One and two false reports: still allowed to send.
    for rid in ids[:2]:
        assert client.post(f"/api/responder/reports/{rid}/mark-false", headers=H_RESP, json={"reason": "prank call"}).status_code == 200
    assert send(bad, "help").status_code == 201  # a 4th report is still allowed (only 2 are false)
    assert not _blocked(bad)
    # The third false report blocks the phone.
    assert client.post(f"/api/responder/reports/{ids[2]}/mark-false", headers=H_RESP, json={"reason": "prank call again"}).status_code == 200
    assert _blocked(bad)
    for kind in ("help", "hazard"):
        r = send(bad, kind)
        assert r.status_code == 403 and "911" in r.json()["detail"]
    # The blocked phone can still read its own reports; another phone is not affected.
    assert len(mine(bad)) == 4
    assert send(good, "help").status_code == 201
    assert ("Rey Responder", "report.phone_blocked", f"phone:{report_service.hash_phone_id(bad)[:8]}") in audit_actions()
    # The audit log never holds the phone ID itself.
    db = db_session()
    try:
        assert not any(bad in (a.detail or "") or bad in (a.target or "") for a in db.query(AuditLog).all())
    finally:
        db.close()


def test_three_false_reports_from_different_phones_do_not_block_anyone():
    phones = [new_phone() for _ in range(3)]
    for p in phones:
        rid = send(p, "help").json()["id"]
        client.post(f"/api/responder/reports/{rid}/mark-false", headers=H_RESP, json={"reason": "not real"})
    assert not any(_blocked(p) for p in phones)
    assert all(send(p, "help").status_code == 201 for p in phones)


def _blocked(phone):
    db = db_session()
    try:
        return report_service.is_blocked(db, report_service.hash_phone_id(phone))
    finally:
        db.close()


def test_marking_a_hazard_false_counts_once_for_each_phone_in_it():
    _clean_slate_hazards()
    phones = [new_phone() for _ in range(3)]
    for p in phones:
        send(p, "hazard")
    item = staff_list(kind="hazard")["items"][0]
    assert item["report_count"] == 3
    r = client.post(f"/api/responder/reports/{item['id']}/mark-false", headers=H_RESP, json={"reason": "Nothing there"})
    assert r.status_code == 200 and r.json()["status"] == "false"
    assert nearby(HOME) == []
    db = db_session()
    try:
        for p in phones:
            assert db.query(Report).filter(Report.phone_hash == report_service.hash_phone_id(p), Report.status == "false").count() == 1
    finally:
        db.close()


# --------------------------------------------------------------------------- responder list

def test_responder_list_flags_new_help_requests():
    # Close whatever earlier checks left open, so the counts below are exact.
    for item in staff_list()["items"]:
        client.post(f"/api/responder/reports/{item['id']}/resolve", headers=H_RESP, json={"what_was_done": "test clean-up"})
    empty = staff_list()
    assert empty["has_new_help"] is False and empty["new_help_count"] == 0 and empty["items"] == []
    assert empty["refresh_seconds"] == config.RESPONDER_REFRESH_SECONDS == 10

    h1 = send(new_phone(), "help", where=HOME).json()["id"]
    hz = send(new_phone(), "hazard", where=FAR).json()["id"]
    h2 = send(new_phone(), "help", where=NEAR).json()["id"]
    data = staff_list()
    assert data["has_new_help"] is True and data["new_help_count"] == 2
    assert data["latest_report_id"] == h2
    # Help requests nobody has taken come first, longest waiting first; then the hazard.
    assert [i["id"] for i in data["items"]] == [h1, h2, hz]
    assert [i["is_new_help"] for i in data["items"]] == [True, True, False]

    client.post(f"/api/responder/reports/{h1}/take", headers=H_RESP)
    data = staff_list()
    assert data["new_help_count"] == 1 and data["has_new_help"] is True
    assert next(i for i in data["items"] if i["id"] == h1)["is_new_help"] is False
    client.post(f"/api/responder/reports/{h2}/take", headers=H_RESP)
    assert staff_list()["has_new_help"] is False  # the red alert goes away
    # Filters; closed reports only when asked for.
    assert [i["kind"] for i in staff_list(kind="hazard")["items"]] == ["hazard"]
    client.post(f"/api/responder/reports/{h1}/resolve", headers=H_RESP, json={"what_was_done": "Done"})
    assert h1 not in [i["id"] for i in staff_list()["items"]]
    assert h1 in [i["id"] for i in staff_list(include_closed=True)["items"]]


# --------------------------------------------------------------------------- roles

def test_roles_on_the_report_routes():
    rid = send(new_phone(), "help").json()["id"]
    routes = [
        ("get", "/api/responder/reports", None),
        ("post", f"/api/responder/reports/{rid}/take", None),
        ("post", f"/api/responder/reports/{rid}/resolve", {"what_was_done": "x done"}),
        ("post", f"/api/responder/reports/{rid}/mark-false", {"reason": "x reason"}),
        ("post", f"/api/responder/reports/{rid}/verify", None),
    ]
    for method, path, body in routes:
        # No token, a made-up token: 401.
        assert getattr(client, method)(path, **({"json": body} if body else {})).status_code == 401, path
        bad = getattr(client, method)(path, headers={"Authorization": "Bearer nope"}, **({"json": body} if body else {}))
        assert bad.status_code == 401, path
    # Nothing changed.
    db = db_session()
    try:
        assert db.get(Report, rid).status == "new"
    finally:
        db.close()
    # The public phone ID is not a staff sign-in.
    assert client.get("/api/responder/reports", headers={"X-Phone-Id": new_phone()}).status_code == 401
    # Responder and Super admin both get through.
    assert client.get("/api/responder/reports", headers=H_RESP).status_code == 200
    assert client.get("/api/responder/reports", headers=H_ADMIN).status_code == 200
    assert client.post(f"/api/responder/reports/{rid}/take", headers=H_ADMIN).status_code == 200
    # A locked-out (signed out) token stops working.
    token = auth("Ria Responder")
    client.post("/api/auth/sign-out", headers=token)
    assert client.get("/api/responder/reports", headers=token).status_code == 401


# --------------------------------------------------------------------------- limits

def test_report_limits_per_phone_ip_and_cooldown():
    old = (config.REPORT_PHONE_COOLDOWN_SECONDS, config.REPORT_PHONE_MAX, config.REPORT_IP_MAX)
    try:
        # Cooldown: one report of each kind per phone.
        report_limiter.reset()
        config.REPORT_PHONE_COOLDOWN_SECONDS = 60
        p = new_phone()
        assert send(p, "help").status_code == 201
        r = send(p, "help")
        assert r.status_code == 429 and "Retry-After" in r.headers
        assert send(p, "hazard", where=FAR).status_code == 201  # the other kind has its own cooldown

        # Per phone.
        report_limiter.reset()
        config.REPORT_PHONE_COOLDOWN_SECONDS, config.REPORT_PHONE_MAX = 0, 2
        p = new_phone()
        assert [send(p, "help").status_code for _ in range(3)] == [201, 201, 429]
        assert send(new_phone(), "help").status_code == 201  # another phone is fine

        # Per IP (all test calls come from one IP).
        report_limiter.reset()
        config.REPORT_PHONE_MAX, config.REPORT_IP_MAX = 1000, 3
        assert [send(new_phone(), "help").status_code for _ in range(4)] == [201, 201, 201, 429]
    finally:
        config.REPORT_PHONE_COOLDOWN_SECONDS, config.REPORT_PHONE_MAX, config.REPORT_IP_MAX = old
        report_limiter.reset()


def test_a_refused_report_does_not_use_up_the_allowance():
    old = config.REPORT_PHONE_MAX
    config.REPORT_PHONE_MAX = 1
    report_limiter.reset()
    try:
        p = new_phone()
        assert send(p, "help", note="x" * 500).status_code == 422  # invalid: refused before the limit
        assert send(p, "help").status_code == 201
    finally:
        config.REPORT_PHONE_MAX = old
        report_limiter.reset()


def test_read_limits():
    old = config.REPORT_READ_MAX
    config.REPORT_READ_MAX = 3
    read_limiter.reset()
    try:
        p = new_phone()
        codes = [client.get("/api/reports/mine", headers={"X-Phone-Id": p}).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429], codes
    finally:
        config.REPORT_READ_MAX = old
        read_limiter.reset()


def test_nearby_checks_its_numbers():
    assert client.get("/api/hazards/nearby").status_code == 422
    assert client.get("/api/hazards/nearby", params={"latitude": 95, "longitude": 121}).status_code == 422
    assert client.get("/api/hazards/nearby", params={"latitude": "nan", "longitude": 121}).status_code == 422


# --------------------------------------------------------------------------- purge

def test_purge_deletes_reports_after_the_retention_time():
    db = db_session()
    try:
        blocked_before = db.query(BlockedPhone).count()
    finally:
        db.close()
    phone = new_phone()
    old_id = send(phone, "help", contact="0917 OLD OLD").json()["id"]
    edge_id = send(phone, "help").json()["id"]
    fresh_id = send(phone, "help").json()["id"]
    set_created_at(old_id, config.REPORTS_KEEP_DAYS + 1)
    set_created_at(edge_id, config.REPORTS_KEEP_DAYS - 1)

    db = db_session()
    try:
        deleted = report_service.purge_old_reports(db)
        assert deleted >= 1
        assert db.get(Report, old_id) is None
        assert db.get(Report, edge_id) is not None and db.get(Report, fresh_id) is not None
        assert db.query(BlockedPhone).count() == blocked_before  # blocks are kept
        # Running it again deletes nothing and is harmless.
        assert report_service.purge_old_reports(db) == 0
    finally:
        db.close()
    assert old_id not in [m["id"] for m in mine(phone)]
    assert ("(system)", "report.purge", None) in audit_actions()

    # The days are a setting, and the same function can be run with a later "now".
    db = db_session()
    try:
        later = report_service._now() + timedelta(days=config.REPORTS_KEEP_DAYS + 1)
        assert report_service.purge_old_reports(db, now=later) >= 2  # edge and fresh are old by then
        assert db.get(Report, edge_id) is None and db.get(Report, fresh_id) is None
    finally:
        db.close()


def test_purge_also_works_for_hazard_groups_and_blocks_survive():
    _clean_slate_hazards()
    phones = [new_phone() for _ in range(3)]
    ids = [send(p, "hazard").json()["id"] for p in phones]
    # The first report is old, the others are newer: the hazard still works with its first report gone.
    set_created_at(ids[0], config.REPORTS_KEEP_DAYS + 5)
    db = db_session()
    try:
        assert report_service.purge_old_reports(db) >= 1
    finally:
        db.close()
    item = staff_list(kind="hazard")["items"][0]
    assert item["report_count"] == 2 and item["phones"] == 2
    assert client.post(f"/api/responder/reports/{item['id']}/take", headers=H_RESP).status_code == 200

    # A blocked phone stays blocked after its reports are purged.
    bad = new_phone()
    for _ in range(3):
        rid = send(bad, "help").json()["id"]
        client.post(f"/api/responder/reports/{rid}/mark-false", headers=H_RESP, json={"reason": "prank"})
    assert _blocked(bad)
    db = db_session()
    try:
        report_service.purge_old_reports(db, now=report_service._now() + timedelta(days=config.REPORTS_KEEP_DAYS + 1))
    finally:
        db.close()
    assert mine(bad) == [] and _blocked(bad) and send(bad, "help").status_code == 403


def test_purge_script_runs():
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "purge_reports.py"
    env = dict(os.environ)
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, cwd=script.parent.parent)
    assert out.returncode == 0, out.stderr
    assert "Deleted" in out.stdout and "report(s)" in out.stdout


# --------------------------------------------------------------------------- part 2b: category, people, can_move

def test_category_is_required_and_limited():
    phone = new_phone()
    body = {"kind": "hazard", "latitude": HOME[0], "longitude": HOME[1]}
    post = lambda b: client.post("/api/reports", headers={"X-Phone-Id": phone}, json=b)  # noqa: E731
    assert post(body).status_code == 422  # missing
    for bad in ("", "   ", "x" * (config.REPORT_CATEGORY_MAX + 1)):
        assert post({**body, "category": bad}).status_code == 422, repr(bad)
    ok = post({**body, "category": "  Fallen   tree or pole "})
    assert ok.status_code == 201, ok.text
    assert mine(phone)[0]["category"] == "Fallen tree or pole"  # trimmed, single spaces
    assert post({**body, "category": "x" * config.REPORT_CATEGORY_MAX}).status_code in (200, 201)  # 40 is allowed


def test_contact_is_required_for_help_and_optional_for_hazards():
    phone = new_phone()
    base = {"kind": "help", "category": "Trapped", "latitude": HOME[0], "longitude": HOME[1]}
    for extra in ({}, {"contact": ""}, {"contact": "   "}, {"contact": None}):
        r = client.post("/api/reports", headers={"X-Phone-Id": phone}, json={**base, **extra})
        assert r.status_code == 422 and "contact" in json.dumps(r.json()).lower(), (extra, r.text)
    assert mine(phone) == []
    assert send(phone, "help", contact="0917 123 4567").status_code == 201
    haz = {"kind": "hazard", "category": "Landslide", "latitude": FAR[0], "longitude": FAR[1]}
    assert client.post("/api/reports", headers={"X-Phone-Id": new_phone()}, json=haz).status_code == 201  # no contact: fine
    assert send(new_phone(), "hazard", where=FAR, contact="0917 555 6666").status_code in (200, 201)


def test_people_and_can_move_are_for_help_requests_only():
    phone = new_phone()
    # Allowed on a help request, and both are optional.
    assert send(phone, "help", people=1, can_move="yes").status_code == 201
    assert send(phone, "help", people=999, can_move="no").status_code == 201
    assert send(phone, "help", can_move="unsure").status_code == 201
    assert send(phone, "help").status_code == 201
    # Wrong values.
    for extra in ({"people": 0}, {"people": 1000}, {"people": -3}, {"people": 2.5}, {"people": "3"},
                  {"people": True}, {"can_move": "maybe"}, {"can_move": ""}, {"can_move": "Yes"}):
        r = send(phone, "help", **extra)
        assert r.status_code == 422, f"{extra} gave {r.status_code}"
    # Refused on a hazard, with a message that says why.
    for extra, word in (({"people": 2}, "people"), ({"can_move": "yes"}, "can_move")):
        r = send(phone, "hazard", **extra)
        assert r.status_code == 422, extra
        assert word in json.dumps(r.json()) and "help request" in json.dumps(r.json())
    # Anything else is still refused.
    assert send(phone, "help", injured=2).status_code == 422
    assert send(phone, "help", name="Juan").status_code == 422


def test_responders_see_category_people_and_can_move_the_public_does_not():
    _clean_slate_hazards()
    phone, other = new_phone(), new_phone()
    r = send(phone, "help", category="Need rescue", people=4, can_move="unsure", contact="0917 PRIVATE 1")
    assert r.status_code == 201
    rid = r.json()["id"]
    item = next(i for i in staff_list()["items"] if i["id"] == rid)
    assert (item["category"], item["people"], item["can_move"]) == ("Need rescue", 4, "unsure")
    assert item["categories"] == ["Need rescue"]
    # The action responses carry the same fields.
    taken = client.post(f"/api/responder/reports/{rid}/take", headers=H_RESP).json()
    assert (taken["category"], taken["people"], taken["can_move"]) == ("Need rescue", 4, "unsure")
    # The sender sees their own category, but not the head count or can_move or the contact.
    mine_now = next(m for m in mine(phone) if m["id"] == rid)
    assert mine_now["category"] == "Need rescue"
    assert not ({"people", "can_move", "contact"} & set(mine_now))
    # The public sees none of it.
    assert mine(other) == [] and nearby(HOME) == []
    for text in (client.get("/api/facilities").text, json.dumps(nearby(HOME, other))):
        assert "Need rescue" not in text and "PRIVATE" not in text
    # A hazard item has no people / can_move.
    hz = send(new_phone(), "hazard", where=FAR, category="Landslide").json()["id"]
    hz_item = next(i for i in staff_list(kind="hazard")["items"] if i["id"] == hz)
    assert hz_item["category"] == "Landslide" and hz_item["people"] is None and hz_item["can_move"] is None
    # Close what this check opened.
    client.post(f"/api/responder/reports/{rid}/resolve", headers=H_RESP, json={"what_was_done": "test clean-up"})
    client.post(f"/api/responder/reports/{hz}/resolve", headers=H_RESP, json={"what_was_done": "test clean-up"})


def test_hazards_group_whatever_the_category():
    _clean_slate_hazards()
    cats = ["Flooded road", "Blocked road", "Other"]
    phones = [new_phone() for _ in cats]
    for i, (p, c) in enumerate(zip(phones, cats)):
        assert send(p, "hazard", where=(HOME[0] + 0.0002 * i, HOME[1]), category=c).status_code == 201  # all within ~45 m
    items = staff_list(kind="hazard")["items"]
    assert len(items) == 1 and items[0]["report_count"] == 3 and items[0]["phones"] == 3
    assert items[0]["category"] == "Flooded road"  # the first report's
    assert items[0]["categories"] == cats
    spots = nearby(HOME)
    assert len(spots) == 1 and spots[0]["status"] == "unconfirmed" and spots[0]["category"] == "Flooded road"
    assert set(spots[0]) == {"id", "latitude", "longitude", "status", "label", "category"}
    # The same phone sending a different category for the same place still counts once.
    again = send(phones[0], "hazard", category="Landslide")
    assert again.status_code == 200
    assert staff_list(kind="hazard")["items"][0]["report_count"] == 3


def test_an_older_database_gets_the_new_columns_and_keeps_its_reports():
    """A reports table made by part 2 (no category / people / can_move) is upgraded on start."""
    import sqlite3
    import subprocess
    old_db = Path(_tmp) / "old-part2.db"
    con = sqlite3.connect(old_db)
    con.executescript("""
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY, kind VARCHAR NOT NULL, status VARCHAR NOT NULL, phone_hash VARCHAR NOT NULL,
            ip_hash VARCHAR NOT NULL, latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, contact VARCHAR,
            note VARCHAR(140), group_id INTEGER, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
            taken_by VARCHAR, taken_at DATETIME, closed_by VARCHAR, closed_at DATETIME,
            resolution_note TEXT, false_reason TEXT, verified_by VARCHAR, verified_at DATETIME);
        INSERT INTO reports (kind, status, phone_hash, ip_hash, latitude, longitude, contact, note, created_at, updated_at)
            VALUES ('help', 'new', 'oldphone', 'x', 13.75, 121.05, '0917 OLD', 'from part 2', datetime('now'), datetime('now'));
    """)
    con.commit()
    con.close()
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app.main import app\n"
        "from app.database import SessionLocal\n"
        "from app.models import Report\n"
        "db = SessionLocal(); r = db.query(Report).one()\n"
        "print(r.note, r.category, r.people, r.can_move)\n"
        "from app import report_service, database\n"
        "print('again', report_service.upgrade_report_columns(database.engine))\n"
    ) % str(Path(__file__).resolve().parent.parent)
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{old_db}")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    assert "from part 2 None None None" in out.stdout  # old row kept, new columns empty
    assert "again []" in out.stdout  # a second start adds nothing
    cols = {row[1] for row in sqlite3.connect(old_db).execute("PRAGMA table_info(reports)")}
    assert {"category", "people", "can_move"} <= cols


def test_existing_endpoints_still_work():
    assert client.get("/api/health").status_code == 200
    assert len(client.get("/api/facilities").json()) > 0


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
