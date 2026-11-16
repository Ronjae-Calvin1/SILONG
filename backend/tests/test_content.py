"""
Part 4 checks: weather, advisories, official sources, emergency numbers and the chatbot placeholder.

Run from the backend folder (needs `pip install -r requirements-dev.txt` once):

    py tests/test_content.py

or every test file in turn (accounts, reports, places, content):

    py tests/run_all.py

It uses its own temporary database, so typhoon.db is never touched. The real Open-Meteo service is
NEVER called: the one network function of the weather module is replaced in every test.
"""
import json
import logging
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

# Must be set BEFORE the app is imported: own database, no limits in the way.
_tmp = tempfile.mkdtemp(prefix="silong-content-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["SIGNIN_IP_MAX_ATTEMPTS"] = "1000"
os.environ["WEATHER_RETRY_SECONDS"] = "0"
os.environ["CHAT_IP_MAX_QUESTIONS"] = "1000"
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts, chat_service, config, weather_service  # noqa: E402
from app.database import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, CachedResponse  # noqa: E402
from app.rate_limit import chat_limiter  # noqa: E402

client = TestClient(app)
PASSWORD = "correct horse 1"


def make_user(name, role):
    db = SessionLocal()
    try:
        return accounts.create_user(db, name, PASSWORD, role, actor="test setup").id
    finally:
        db.close()


def auth(name):
    r = client.post("/api/auth/sign-in", json={"name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


ADMIN_NAME = "Cara Content Admin"
make_user(ADMIN_NAME, "super_admin")
make_user("Rey Content Responder", "responder")
H_ADMIN, H_RESP = auth(ADMIN_NAME), auth("Rey Content Responder")
NO_AUTH = {}


# ---------------------------------------------------------------- helpers

def sample_reply(temp=28.4, code=61):
    """What Open-Meteo sends (the parts we read)."""
    return {
        "current": {
            "time": "2026-11-16T15:00", "temperature_2m": temp, "relative_humidity_2m": 84,
            "apparent_temperature": 33.1, "precipitation": 1.2, "weather_code": code,
            "wind_speed_10m": 22.5, "wind_gusts_10m": 41.0, "is_day": 1,
        },
        "daily": {
            "time": ["2026-11-16", "2026-11-17", "2026-11-18"],
            "weather_code": [61, 80, 3],
            "temperature_2m_max": [31.0, 30.2, 31.5], "temperature_2m_min": [25.1, 24.8, 25.0],
            "precipitation_sum": [8.4, 3.1, 0.0], "precipitation_probability_max": [80, 60, 20],
            "wind_speed_10m_max": [30.1, 25.0, 18.2],
        },
    }


class FakeNet:
    """Replaces the weather network call. `replies` are used in order; an Exception in it is raised."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def __call__(self, url, timeout):
        self.calls += 1
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


@contextmanager
def weather_net(*replies):
    fake = FakeNet(*replies)
    with mock.patch.object(weather_service, "_http_get_json", fake):
        yield fake


def fresh_weather(clear_saved_copy=True):
    weather_service.reset()
    if clear_saved_copy:
        db = SessionLocal()
        db.query(CachedResponse).filter(CachedResponse.key == weather_service.CACHE_KEY).delete()
        db.commit()
        db.close()


def table_counts():
    db = SessionLocal()
    try:
        return {t.name: db.execute(t.select().with_only_columns(__import__("sqlalchemy").func.count())).scalar() for t in Base.metadata.sorted_tables}
    finally:
        db.close()


def audit_actions(prefix=""):
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter(AuditLog.action.like(f"{prefix}%")).order_by(AuditLog.id).all()
        return [(r.action, r.actor_name, r.actor_role, r.target) for r in rows]
    finally:
        db.close()


ADV = {"title": "Wind Signal No. 2 raised", "details": "Damaging winds expected. Secure loose items.",
       "organization": "PAGASA", "source_url": "https://www.pagasa.dost.gov.ph/bulletin/1"}


def new_advisory(**changes):
    r = client.post("/api/admin/advisories", json={**ADV, **changes}, headers=H_ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


def plain(detail):
    """No developer words in a message people will read."""
    text = json.dumps(detail).lower()
    return not any(w in text for w in ("traceback", "exception", "urlerror", "sqlalchemy", "none"))


# ---------------------------------------------------------------- weather

def test_weather_is_real_data_in_the_shape_the_screen_needs_and_is_cached():
    fresh_weather()
    with weather_net(sample_reply()) as net:
        r = client.get("/api/weather")
        assert r.status_code == 200, r.text
        w = r.json()
        assert w["location"] == "Batangas City" and w["is_stale"] is False and w["notice"] is None
        assert w["current"]["temperature_c"] == 28.4 and w["current"]["wind_kph"] == 22.5
        assert w["current"]["condition"] == "Light rain" and w["current"]["rain_mm"] == 1.2
        assert [d["date"] for d in w["daily"]] == ["2026-11-16", "2026-11-17", "2026-11-18"]
        assert w["daily"][1]["condition"] == "Light rain showers" and w["daily"][0]["rain_chance_percent"] == 80
        assert w["cyclone"] is None  # WeatherTab then says "Not available right now. Check PAGASA."
        assert w["strip"] == {"headline": "28°C · Light rain", "detail": "Tap to open alerts · Batangas City"}
        assert w["fetched_at"].endswith("Z") or "+00:00" in w["fetched_at"]
        # A second request inside the cache time does not ask Open-Meteo again.
        assert client.get("/api/weather").json()["fetched_at"] == w["fetched_at"]
        assert net.calls == 1
    # No key and no login are needed.
    assert "Authorization" not in client.get("/api/weather").request.headers


def test_weather_falls_back_to_the_last_good_forecast_when_the_call_fails():
    fresh_weather()
    with weather_net(sample_reply(temp=27.0)):
        good = client.get("/api/weather").json()
    with mock.patch.object(config, "WEATHER_CACHE_MINUTES", 0):  # the cached copy counts as old: ask again
        with weather_net(urllib.error.URLError("no internet")) as net:
            r = client.get("/api/weather")
            assert net.calls == 1  # it did try
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["is_stale"] is True and w["current"]["temperature_c"] == 27.0
    assert w["fetched_at"] == good["fetched_at"]  # the time of the good forecast, not now
    assert "last one we received" in w["notice"] and plain(w["notice"])
    assert w["strip"]["detail"].startswith("Old forecast")
    # A reply with a missing value is a failed call too: never filled in with zeros.
    broken = sample_reply()
    broken["current"]["temperature_2m"] = None
    with mock.patch.object(config, "WEATHER_CACHE_MINUTES", 0), weather_net(broken):
        w2 = client.get("/api/weather").json()
    assert w2["is_stale"] is True and w2["current"]["temperature_c"] == 27.0


def test_weather_gives_a_clear_error_when_there_has_never_been_a_forecast():
    fresh_weather()
    with weather_net(OSError("no internet")):
        r = client.get("/api/weather")
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "can't get the weather" in detail and "PAGASA" in detail and plain(detail)
    assert "current" not in r.json()  # no numbers at all
    # An unreadable reply (no "current" part) is the same.
    fresh_weather()
    with weather_net({"hello": "world"}):
        assert client.get("/api/weather").status_code == 503


def test_the_last_good_forecast_survives_a_restart():
    fresh_weather()
    with weather_net(sample_reply(temp=26.0)):
        first = client.get("/api/weather").json()
    weather_service.reset()  # memory is gone, like after a restart; the database copy stays
    with mock.patch.object(config, "WEATHER_CACHE_MINUTES", 0), weather_net(OSError("down")):
        w = client.get("/api/weather").json()
    assert w["is_stale"] is True and w["current"]["temperature_c"] == 26.0 and w["fetched_at"] == first["fetched_at"]


def test_a_day_with_a_missing_number_is_left_out_not_invented():
    fresh_weather()
    reply = sample_reply()
    reply["daily"]["temperature_2m_max"][1] = None
    with weather_net(reply):
        days = client.get("/api/weather").json()["daily"]
    assert [d["date"] for d in days] == ["2026-11-16", "2026-11-18"]


# ---------------------------------------------------------------- permissions

def test_only_a_super_admin_can_change_advisories_sources_and_numbers():
    adv = new_advisory(title="Permission check advisory")["id"]
    num = client.post("/api/admin/emergency-numbers", json={"number": "8888", "name": "Permission check"}, headers=H_ADMIN).json()["id"]
    src = client.post("/api/admin/advisory-sources", json={"name": "Permission Check Agency"}, headers=H_ADMIN).json()["id"]
    before = table_counts()
    audit_before = len(audit_actions())
    calls = [
        ("post", "/api/admin/advisories", ADV),
        ("patch", f"/api/admin/advisories/{adv}", {"title": "Changed"}),
        ("post", f"/api/admin/advisories/{adv}/pin", None),
        ("post", f"/api/admin/advisories/{adv}/unpin", None),
        ("delete", f"/api/admin/advisories/{adv}", None),
        ("get", "/api/admin/advisory-sources", None),
        ("post", "/api/admin/advisory-sources", {"name": "Sneaky Source"}),
        ("patch", f"/api/admin/advisory-sources/{src}", {"name": "Sneaky Rename"}),
        ("delete", f"/api/admin/advisory-sources/{src}", None),
        ("post", "/api/admin/emergency-numbers", {"number": "7777", "name": "Sneaky"}),
        ("patch", f"/api/admin/emergency-numbers/{num}", {"name": "Sneaky"}),
        ("put", "/api/admin/emergency-numbers/order", {"ids": [num]}),
        ("delete", f"/api/admin/emergency-numbers/{num}", None),
    ]
    for method, path, body in calls:
        for who, headers, status in (("the public", NO_AUTH, 401), ("a responder", H_RESP, 403)):
            r = client.request(method.upper(), path, json=body, headers=headers) if body is not None else client.request(method.upper(), path, headers=headers)
            assert r.status_code == status, f"{who} {method} {path}: {r.status_code} {r.text}"
    assert table_counts() == before  # nothing changed
    assert len(audit_actions()) == audit_before  # and nothing was logged as done
    # The Super admin passes the same checks.
    assert client.patch(f"/api/admin/advisories/{adv}", json={"title": "Changed by admin"}, headers=H_ADMIN).status_code == 200


# ---------------------------------------------------------------- advisories

def test_public_reads_work_without_signing_in_and_pinned_comes_first():
    a = new_advisory(title="Order A old")["id"]
    b = new_advisory(title="Order B middle")["id"]
    c = new_advisory(title="Order C newest")["id"]
    assert client.post(f"/api/admin/advisories/{a}/pin", headers=H_ADMIN).json()["pinned"] is True
    r = client.get("/api/advisories")  # no sign-in
    assert r.status_code == 200
    mine = [x["id"] for x in r.json() if x["id"] in (a, b, c)]
    assert mine == [a, c, b]  # pinned first, then newest
    first = r.json()[0]
    assert first["pinned"] is True
    # the fields AlertsSheet's tabs read
    assert set(first) >= {"id", "title", "details", "summary", "organization", "source_url", "is_official", "pinned", "published_at"}
    assert first["summary"] == first["details"]
    # unpinned: back to newest first
    assert client.post(f"/api/admin/advisories/{a}/unpin", headers=H_ADMIN).json()["pinned"] is False
    assert [x["id"] for x in client.get("/api/advisories").json() if x["id"] in (a, b, c)] == [c, b, a]
    assert client.get("/api/emergency-numbers").status_code == 200  # public too


def test_only_listed_sources_are_official_and_the_list_is_editable():
    names = [s["name"] for s in client.get("/api/admin/advisory-sources", headers=H_ADMIN).json()]
    assert {"PAGASA", "NDRRMC", "Batangas City CDRRMO"} <= set(names)
    off = new_advisory(title="From PAGASA", organization="  pagasa ")["id"]  # case and spaces do not matter
    other = new_advisory(title="From a page", organization="Batangas News Page")["id"]
    by_id = {x["id"]: x for x in client.get("/api/advisories").json()}
    assert by_id[off]["is_official"] is True and by_id[other]["is_official"] is False
    only = [x["id"] for x in client.get("/api/advisories?official=true").json()]
    assert off in only and other not in only
    # a Super admin adds the page to the list: it counts now, also for the old advisory
    s = client.post("/api/admin/advisory-sources", json={"name": "Batangas News Page"}, headers=H_ADMIN)
    assert s.status_code == 201
    assert client.post("/api/admin/advisory-sources", json={"name": "batangas   news page"}, headers=H_ADMIN).status_code == 409
    assert {x["id"]: x for x in client.get("/api/advisories").json()}[other]["is_official"] is True
    assert client.delete(f"/api/admin/advisory-sources/{s.json()['id']}", headers=H_ADMIN).status_code == 204
    assert {x["id"]: x for x in client.get("/api/advisories").json()}[other]["is_official"] is False


def test_advisory_fields_are_checked_with_plain_messages():
    for bad, words in (
        ({"source_url": "javascript:alert(1)"}, "http"),
        ({"source_url": "www.example.com"}, "http"),
        ({"title": "   "}, "cannot be empty"),
        ({"title": "T" * (config.ADVISORY_TITLE_MAX + 1)}, "too long"),
        ({"details": ""}, "cannot be empty"),
        ({"organization": ""}, "cannot be empty"),
    ):
        r = client.post("/api/admin/advisories", json={**ADV, **bad}, headers=H_ADMIN)
        assert r.status_code == 422, (bad, r.text)
        assert words in json.dumps(r.json()), (bad, r.text)
    assert client.post("/api/admin/advisories", json={**ADV, "extra": 1}, headers=H_ADMIN).status_code == 422
    adv = new_advisory(title="Edit me")["id"]
    assert client.patch(f"/api/admin/advisories/{adv}", json={}, headers=H_ADMIN).status_code == 422
    assert client.patch("/api/admin/advisories/999999", json={"title": "x"}, headers=H_ADMIN).status_code == 404
    r = client.patch(f"/api/admin/advisories/{adv}", json={"title": "Edited", "source_url": "https://ndrrmc.gov.ph/x"}, headers=H_ADMIN)
    assert r.status_code == 200 and r.json()["title"] == "Edited" and r.json()["updated_at"]
    assert client.delete(f"/api/admin/advisories/{adv}", headers=H_ADMIN).status_code == 204
    assert client.delete(f"/api/admin/advisories/{adv}", headers=H_ADMIN).status_code == 404


# ---------------------------------------------------------------- emergency numbers

def test_emergency_numbers_start_with_911_only_and_a_super_admin_edits_them():
    start = client.get("/api/emergency-numbers").json()
    assert [(n["number"], n["name"]) for n in start][:1] == [("911", "National Emergency")]
    assert not any(n["number"] in ("143", "(043) 723-0165") for n in start)  # nothing unconfirmed was copied in
    a = client.post("/api/admin/emergency-numbers", json={"number": "(043) 111-2222", "name": "Order test A", "description": "Test only"}, headers=H_ADMIN)
    b = client.post("/api/admin/emergency-numbers", json={"number": "1234", "name": "Order test B"}, headers=H_ADMIN)
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    a, b = a.json(), b.json()
    assert a["position"] < b["position"]
    r = client.patch(f"/api/admin/emergency-numbers/{a['id']}", json={"name": "Order test A2", "description": None}, headers=H_ADMIN)
    assert r.status_code == 200 and r.json()["name"] == "Order test A2" and r.json()["description"] is None
    ids = [n["id"] for n in client.get("/api/emergency-numbers").json()]
    new_order = [b["id"]] + [i for i in ids if i != b["id"]]
    r = client.put("/api/admin/emergency-numbers/order", json={"ids": new_order}, headers=H_ADMIN)
    assert r.status_code == 200 and [n["id"] for n in r.json()] == new_order
    assert [n["id"] for n in client.get("/api/emergency-numbers").json()] == new_order
    assert client.put("/api/admin/emergency-numbers/order", json={"ids": new_order[:-1]}, headers=H_ADMIN).status_code == 422
    assert client.put("/api/admin/emergency-numbers/order", json={"ids": new_order + new_order[:1]}, headers=H_ADMIN).status_code == 422
    for bad in ({"number": "ab", "name": "x"}, {"number": "12", "name": "x"}, {"number": "911", "name": " "}, {"number": "tel:911", "name": "x"}):
        assert client.post("/api/admin/emergency-numbers", json=bad, headers=H_ADMIN).status_code == 422, bad
    assert client.delete(f"/api/admin/emergency-numbers/{a['id']}", headers=H_ADMIN).status_code == 204
    assert client.delete(f"/api/admin/emergency-numbers/{b['id']}", headers=H_ADMIN).status_code == 204
    assert client.delete(f"/api/admin/emergency-numbers/{b['id']}", headers=H_ADMIN).status_code == 404


# ---------------------------------------------------------------- audit

def test_every_admin_action_is_in_the_audit_log_with_the_persons_name():
    adv = new_advisory(title="Audit advisory")["id"]
    client.patch(f"/api/admin/advisories/{adv}", json={"details": "Changed text."}, headers=H_ADMIN)
    client.post(f"/api/admin/advisories/{adv}/pin", headers=H_ADMIN)
    client.post(f"/api/admin/advisories/{adv}/unpin", headers=H_ADMIN)
    client.delete(f"/api/admin/advisories/{adv}", headers=H_ADMIN)
    src = client.post("/api/admin/advisory-sources", json={"name": "Audit Agency"}, headers=H_ADMIN).json()["id"]
    client.patch(f"/api/admin/advisory-sources/{src}", json={"name": "Audit Agency 2"}, headers=H_ADMIN)
    client.delete(f"/api/admin/advisory-sources/{src}", headers=H_ADMIN)
    num = client.post("/api/admin/emergency-numbers", json={"number": "5555", "name": "Audit number"}, headers=H_ADMIN).json()["id"]
    client.patch(f"/api/admin/emergency-numbers/{num}", json={"number": "5556"}, headers=H_ADMIN)
    ids = [n["id"] for n in client.get("/api/emergency-numbers").json()]
    client.put("/api/admin/emergency-numbers/order", json={"ids": list(reversed(ids))}, headers=H_ADMIN)
    client.delete(f"/api/admin/emergency-numbers/{num}", headers=H_ADMIN)

    mine = {action for action, name, role, target in audit_actions() if name == ADMIN_NAME and role == "super_admin"}
    wanted = {
        "advisory.create", "advisory.update", "advisory.pin", "advisory.unpin", "advisory.delete",
        "advisory_source.add", "advisory_source.update", "advisory_source.remove",
        "emergency_number.add", "emergency_number.update", "emergency_number.reorder", "emergency_number.remove",
    }
    assert wanted <= mine, wanted - mine
    # the entry says what it was done to, and never holds a password or token
    created = [t for a, n, r, t in audit_actions("advisory.create") if "Audit advisory" in (t or "")]
    assert created and created[0].startswith("advisory:")
    # saying the same thing twice does not log a change that did not happen
    adv2 = new_advisory(title="Audit twice")["id"]
    client.post(f"/api/admin/advisories/{adv2}/pin", headers=H_ADMIN)
    n = len(audit_actions("advisory.pin"))
    client.post(f"/api/admin/advisories/{adv2}/pin", headers=H_ADMIN)
    assert len(audit_actions("advisory.pin")) == n


# ---------------------------------------------------------------- chat

class NoNetwork:
    """Any attempt to reach the network fails the test, and is counted."""

    def __enter__(self):
        self.hits = []

        def boom(*a, **k):
            self.hits.append(a)
            raise AssertionError("The chat code must not use the network.")

        self.patches = [
            mock.patch.object(socket.socket, "connect", boom),
            mock.patch.object(socket, "create_connection", boom),
            mock.patch.object(socket, "getaddrinfo", boom),
            mock.patch.object(urllib.request, "urlopen", boom),
            mock.patch.object(weather_service, "_http_get_json", boom),
        ]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


def ask(question, **kw):
    return client.post("/api/chat", json={"question": question}, **kw)


def test_chat_answer_has_the_screen_shape_the_ending_and_makes_no_network_call():
    chat_limiter.reset()
    with NoNetwork() as net:
        r = ask("What should I do during a flood?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"answer", "topic"}  # SiloAnswer: { answer: string; topic: string | null }
    assert isinstance(body["answer"], str) and body["topic"] is None
    assert body["answer"].endswith("AI-generated. Follow official advisories first.")
    assert body["answer"].count("AI-generated. Follow official advisories first.") == 1
    assert "not available yet" in body["answer"] and "911" in body["answer"] and "advisories" in body["answer"]
    assert net.hits == []
    # the same through the entry point, for any question
    assert chat_service.answer("anything").answer.endswith(chat_service.ENDING)


def test_the_ending_is_added_in_one_place_for_every_provider():
    class Plain:
        name = "plain"
        def answer(self, question, timeout):  # noqa: E301
            return chat_service.ChatAnswer("Move to higher ground.", topic="Flood")

    class Forgetful(Plain):
        def answer(self, question, timeout):  # noqa: E301
            return chat_service.ChatAnswer("  Stay calm.  \n", topic=None)

    class AlreadyEnds(Plain):
        def answer(self, question, timeout):  # noqa: E301
            return chat_service.ChatAnswer("Stay calm. " + chat_service.ENDING, topic=None)

    class Broken(Plain):
        def answer(self, question, timeout):  # noqa: E301
            raise RuntimeError("provider is down: secret details")

    class Empty(Plain):
        def answer(self, question, timeout):  # noqa: E301
            return chat_service.ChatAnswer("   ", topic="x")

    providers = {"plain": Plain, "forgetful": Forgetful, "already": AlreadyEnds, "broken": Broken, "empty": Empty}
    with mock.patch.dict(chat_service._PROVIDERS, providers):
        for name in providers:
            with mock.patch.object(config, "CHAT_PROVIDER", name):
                text = chat_service.answer("q").answer
                assert text.endswith(chat_service.ENDING) and text.count(chat_service.ENDING) == 1, (name, text)
        with mock.patch.object(config, "CHAT_PROVIDER", "plain"):
            got = chat_service.answer("q")
            assert got.topic == "Flood" and got.answer.startswith("Move to higher ground.")
        for name in ("broken", "empty"):  # a failing provider means the placeholder, never a crash
            with mock.patch.object(config, "CHAT_PROVIDER", name):
                assert chat_service.PLACEHOLDER_TEXT in chat_service.answer("q").answer


def test_a_provider_that_is_not_built_falls_back_to_the_placeholder_with_one_warning():
    chat_limiter.reset()
    chat_service._warned_about.discard("gemini")
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Catch()
    logging.getLogger("silong.chat").addHandler(handler)
    try:
        with mock.patch.object(config, "CHAT_PROVIDER", "gemini"):
            r1, r2 = ask("Is the road open?"), ask("Where do I go?")
    finally:
        logging.getLogger("silong.chat").removeHandler(handler)
    for r in (r1, r2):
        assert r.status_code == 200, r.text
        assert chat_service.PLACEHOLDER_TEXT in r.json()["answer"] and r.json()["answer"].endswith(chat_service.ENDING)
    warnings = [x for x in records if x.levelno == logging.WARNING]
    assert len(warnings) == 1, [w.getMessage() for w in warnings]
    assert "gemini" in warnings[0].getMessage() and "not built yet" in warnings[0].getMessage()
    assert "Is the road open" not in warnings[0].getMessage()
    # the default really is the placeholder
    assert config.CHAT_PROVIDER == "placeholder"


def test_a_question_that_is_too_long_or_empty_is_refused_with_a_plain_message():
    chat_limiter.reset()
    limit = config.CHAT_MAX_QUESTION_LENGTH
    assert limit == 200  # the chat box on the site counts to 200
    assert ask("a" * limit).status_code == 200
    assert ask("  " + "a" * limit + "  ").status_code == 200  # spaces around it do not count
    r = ask("a" * (limit + 1))
    assert r.status_code == 422
    assert r.json()["detail"] == f"Your question is too long. Please keep it under {limit} characters."
    for empty in ("", "   \n "):
        r = ask(empty)
        assert r.status_code == 422 and r.json()["detail"] == "Please type a question."
    # the limit can be changed with a setting
    with mock.patch.object(config, "CHAT_MAX_QUESTION_LENGTH", 10):
        assert ask("x" * 11).status_code == 422 and ask("x" * 10).status_code == 200


def test_the_chat_endpoint_is_rate_limited_per_ip():
    chat_limiter.reset()
    with mock.patch.object(config, "CHAT_IP_MAX_QUESTIONS", 3):
        assert [ask("One").status_code, ask("Two").status_code, ask("Three").status_code] == [200, 200, 200]
        assert ask("a" * 500).status_code == 422  # a refused question does not use up the allowance
        r = ask("Four")
        assert r.status_code == 429, r.text
        assert "Too many questions" in r.json()["detail"] and plain(r.json()["detail"])
        assert int(r.headers["Retry-After"]) >= 1
    chat_limiter.reset()
    assert ask("After reset").status_code == 200


def test_the_chat_endpoint_stores_nothing_about_the_asker_or_the_question():
    chat_limiter.reset()
    secret = "Where is Zxqvb Unique Barangay shelter?"
    before = table_counts()
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Catch()
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        r = ask(secret, headers={"X-Phone-Id": "phone-chat-00000001-abcdef", "X-Forwarded-For": "203.0.113.9"})
    finally:
        root.setLevel(old_level)
        root.removeHandler(handler)
    assert r.status_code == 200
    assert table_counts() == before  # not one row in any table (also not in the audit log)
    assert not any(secret in m for m in records)  # and not in the log
    # the question is not in the database file either
    raw = (Path(_tmp) / "test.db").read_bytes()
    assert b"Zxqvb" not in raw


# ---------------------------------------------------------------- an older database

OLD_DB_SETUP = """
import os, sqlite3
from sqlalchemy import create_engine
from app.database import Base
from app import models  # noqa: F401
NEW = {"advisories", "advisory_sources", "emergency_numbers"}
engine = create_engine(os.environ["DATABASE_URL"])
Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in NEW])
con = sqlite3.connect(os.environ["DATABASE_URL"].replace("sqlite:///", ""))
con.execute("INSERT INTO cached_responses (key, kind, content) VALUES ('prep_plan:old', 'prep_plan', '{\\"keep\\": true}')")
con.execute("INSERT INTO users (name, name_key, password_hash, role, failed_attempts, is_locked, created_at) VALUES ('Old Staff', 'old staff', 'x', 'responder', 0, 0, datetime('now'))")
con.execute("INSERT INTO audit_log (created_at, actor_name, action) VALUES (datetime('now'), 'Old Staff', 'old.entry')")
con.commit()
"""

OLD_DB_START = """
import json
from unittest import mock
from fastapi.testclient import TestClient
from app import weather_service
from app.database import SessionLocal
from app.main import app
from app.models import AuditLog, CachedResponse, EmergencyNumber, User
c = TestClient(app)
reply = {"current": {"temperature_2m": 29.0, "precipitation": 0.0, "weather_code": 1, "wind_speed_10m": 10.0},
         "daily": {"time": ["2026-11-16"], "weather_code": [1], "temperature_2m_max": [31.0], "temperature_2m_min": [25.0], "precipitation_sum": [0.0]}}
with mock.patch.object(weather_service, "_http_get_json", lambda url, timeout: reply):
    w = c.get("/api/weather")
db = SessionLocal()
print(json.dumps({
    "health": c.get("/api/health").status_code,
    "facilities": len(c.get("/api/facilities").json()) > 0,
    "weather": [w.status_code, w.json().get("current", {}).get("temperature_c")],
    "numbers": [n["number"] for n in c.get("/api/emergency-numbers").json()],
    "advisories": c.get("/api/advisories").json(),
    "old_cache": db.query(CachedResponse).filter(CachedResponse.key == "prep_plan:old").count(),
    "weather_copy": db.query(CachedResponse).filter(CachedResponse.key == "weather:current").count(),
    "users": db.query(User).count(),
    "old_audit": db.query(AuditLog).filter(AuditLog.action == "old.entry").count(),
    "sources": sorted(s["name"] for s in [{"name": r[0]} for r in db.execute(__import__("sqlalchemy").text("SELECT name FROM advisory_sources"))]),
}))
if __import__("os").environ.get("DROP_911"):
    db.query(EmergencyNumber).delete()
    db.execute(__import__("sqlalchemy").text("DELETE FROM advisory_sources WHERE name = 'NDRRMC'"))
    db.commit()
"""


def _run(code, db_path, **extra_env):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db_path}", **extra_env)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=BACKEND, env=env)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_an_older_database_still_starts_gets_the_new_tables_and_keeps_its_data():
    old_db = Path(_tmp) / "old-part3.db"
    _run(OLD_DB_SETUP, old_db)
    tables = {r[0] for r in sqlite3.connect(old_db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not ({"advisories", "advisory_sources", "emergency_numbers"} & tables)  # really an older database

    out = json.loads(_run(OLD_DB_START, old_db, DROP_911="1").strip().splitlines()[-1])
    assert out["health"] == 200 and out["facilities"] is True
    assert out["weather"] == [200, 29.0] and out["weather_copy"] == 1
    assert out["numbers"] == ["911"] and out["advisories"] == []
    assert out["sources"] == ["Batangas City CDRRMO", "NDRRMC", "PAGASA"]
    assert out["old_cache"] == 1 and out["users"] == 1 and out["old_audit"] == 1  # nothing old was lost

    # The starting rows are made once: what a Super admin removed does not come back on the next start.
    out2 = json.loads(_run(OLD_DB_START, old_db).strip().splitlines()[-1])
    assert out2["numbers"] == [] and out2["sources"] == ["Batangas City CDRRMO", "PAGASA"]
    assert out2["old_cache"] == 1 and out2["users"] == 1


def test_the_old_stub_files_and_routes_are_gone_and_existing_endpoints_work():
    assert not (BACKEND / "app" / "ai_service.py").exists() and not (BACKEND / "app" / "routes.py").exists()
    paths = set(app.openapi()["paths"])
    assert not any(p.startswith("/ai/") or p.startswith("/api/ai/") for p in paths)
    assert client.get("/api/health").status_code == 200
    assert len(client.get("/api/facilities").json()) > 0
    assert client.post("/api/auth/sign-in", json={"name": ADMIN_NAME, "password": PASSWORD}).status_code == 200


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
