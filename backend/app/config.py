"""
Tunable settings for the capacity / availability feature.

Everything that is "still to be confirmed" with the project documentation
lives here, in one place. Each value can also be overridden with an
environment variable, which is handy for testing (for example
STATUS_COOLDOWN_SECONDS=0 turns the per-place cooldown off).
"""
import os
from datetime import timedelta
from pathlib import Path


def load_env_file(path, environ=None) -> int:
    """
    Reads a simple KEY=VALUE file into the environment (a tiny .env loader, no extra package).

    - Blank lines and lines starting with # are skipped. An optional leading "export " is ignored.
    - One pair of matching single or double quotes around the value is removed.
    - A variable that is ALREADY set in the real environment is never replaced: the real
      environment always wins over the file.
    - A missing or unreadable file is fine (nothing happens).

    Returns how many variables it set. Never prints or returns a value (a file can hold keys).
    """
    environ = os.environ if environ is None else environ
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return 0
    added = 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key or key in environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        environ[key] = value
        added += 1
    return added


# backend/.env (ignored by Git) is read once, here, before any setting below. This module is the
# first thing the app imports, so the file also reaches DATABASE_URL (database.py imports config).
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_env_file(ENV_FILE)


def _number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


# A status older than this is shown as "May be outdated".
# TO BE CONFIRMED in the project documentation. This is the ONLY place the
# value is defined: the backend computes `is_outdated` and the frontend just
# displays it.
OUTDATED_AFTER = timedelta(hours=_number("STATUS_OUTDATED_AFTER_HOURS", 6))

# ---- CORS: which websites may call this backend from a browser ----
# SILONG runs as two frontends and one backend: the user site (5173) and the admin console (5174).
# Only these origins may read answers in a browser. "*" (any website) is allowed ONLY when it is set
# explicitly in CORS_ORIGINS. Not set, or empty, means the default list below.
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
)


def parse_cors_origins(raw):
    """
    CORS_ORIGINS (comma separated) as a list. Spaces, empty parts and a trailing "/" are dropped, case
    does not matter (browsers send the origin in lower case) and repeats are removed. Nothing usable
    (not set, empty) gives the default list. "*" anywhere in the list means any website.
    """
    origins = []
    for part in (raw or "").split(","):
        origin = part.strip().rstrip("/").lower()
        if origin and origin not in origins:
            origins.append(origin)
    return origins or list(DEFAULT_CORS_ORIGINS)


CORS_ORIGINS = parse_cors_origins(os.getenv("CORS_ORIGINS"))

# ---- Spam protection (no accounts, so we limit by client IP) ----
# At most 1 update per place per IP within this many seconds.
STATUS_COOLDOWN_SECONDS = int(_number("STATUS_COOLDOWN_SECONDS", 60))
# At most this many updates (any place) per IP within the window below.
STATUS_IP_MAX_UPDATES = int(_number("STATUS_IP_MAX_UPDATES", 10))
STATUS_IP_WINDOW_SECONDS = int(_number("STATUS_IP_WINDOW_SECONDS", 600))

# ---- Evacuation center manager (add / remove / restore) ----
# The ONE place the city area is defined: (south, west, north, east) in degrees.
# It is a rough rectangle, wider than the real city limits on purpose (it covers
# every point in data/facilities.json), so it also takes in small parts of the
# neighbouring towns. Tighten it here if that matters; nothing else needs to change.
BATANGAS_CITY_BBOX = (13.60, 120.97, 13.86, 121.18)

# A new center whose normalized name matches an existing one this close (metres)
# is rejected as a duplicate.
DUPLICATE_METERS = 30

# Largest max_capacity accepted for one center (a typo guard, not a real limit).
MAX_CAPACITY_LIMIT = int(_number("MAX_CAPACITY_LIMIT", 50_000))

# Adding a place has one allowance per IP and one per phone ID. (Removing and
# restoring are Admin actions now: signed in and audited, so they are not limited here.)
MANAGE_MAX_ACTIONS = int(_number("MANAGE_MAX_ACTIONS", 10))
MANAGE_WINDOW_SECONDS = int(_number("MANAGE_WINDOW_SECONDS", 600))

# ---- Places: approval and removal (redesign part 3) ----
# A center removed by an Admin is hidden for everyone and kept this many
# days, then deleted together with its status history (see place_service.purge_removed_centers).
# An Admin can delete one sooner. Places an Admin rejected are deleted after the same time.
REMOVED_CENTERS_KEEP_DAYS = int(_number("REMOVED_CENTERS_KEEP_DAYS", 30))

# One phone can have at most this many added places waiting for approval at the same time.
PENDING_PLACES_PER_PHONE = int(_number("PENDING_PLACES_PER_PHONE", 5))

# Salt for the hashed IPs in the action log. Set IP_HASH_SALT in the environment
# to keep hashes comparable across restarts. If it is not set, a random salt is
# made on each start (hashes still hide the IP; they just stop matching old ones).
IP_HASH_SALT = os.getenv("IP_HASH_SALT") or os.urandom(16).hex()

# ---- Admin accounts ----
# Admin sessions end (the name STAFF_IDLE_MINUTES is kept so existing .env files keep working) after this many minutes without any request.
STAFF_IDLE_MINUTES = int(_number("STAFF_IDLE_MINUTES", 30))
# This many wrong passwords in a row lock the account...
SIGNIN_MAX_WRONG_TRIES = int(_number("SIGNIN_MAX_WRONG_TRIES", 5))
# ...for this many minutes. An Admin can unlock it sooner.
SIGNIN_LOCK_MINUTES = int(_number("SIGNIN_LOCK_MINUTES", 15))

# Per-IP limit on sign-in attempts of any account (slows guessing across many
# names; the per-account lock above handles guessing one name).
SIGNIN_IP_MAX_ATTEMPTS = int(_number("SIGNIN_IP_MAX_ATTEMPTS", 20))
SIGNIN_IP_WINDOW_SECONDS = int(_number("SIGNIN_IP_WINDOW_SECONDS", 600))

# Shortest password an Admin can give a new account (a typo guard, not a policy).
MIN_PASSWORD_LENGTH = int(_number("MIN_PASSWORD_LENGTH", 8))

# ---- Help requests and hazard reports (redesign part 2) ----
# Reports (both kinds) are deleted this many days after they were sent.
REPORTS_KEEP_DAYS = int(_number("REPORTS_KEEP_DAYS", 30))

# A hazard shows to the public as "Unconfirmed" once this many DIFFERENT phones
# reported it. An Admin can verify it sooner.
HAZARD_UNCONFIRMED_PHONES = int(_number("HAZARD_UNCONFIRMED_PHONES", 3))

# After this many reports marked false from one phone, that phone cannot send reports.
FALSE_REPORTS_BEFORE_BLOCK = int(_number("FALSE_REPORTS_BEFORE_BLOCK", 3))

# "Near me" range for hazard reports, in kilometres.
NEAR_ME_KM = _number("NEAR_ME_KM", 1)

# The Admin screens poll about this often (seconds). Sent to the screen with every list.
# (The name RESPONDER_REFRESH_SECONDS is kept so existing .env files keep working.)
RESPONDER_REFRESH_SECONDS = int(_number("RESPONDER_REFRESH_SECONDS", 10))

# Hazard reports closer than this (metres) to an open hazard are the same hazard.
HAZARD_MERGE_METERS = int(_number("HAZARD_MERGE_METERS", 100))

# The public sees a hazard only as the middle of a square of this size (metres).
HAZARD_APPROX_METERS = int(_number("HAZARD_APPROX_METERS", 250))

# Longest text accepted in a report.
REPORT_NOTE_MAX = 140
REPORT_CONTACT_MAX = 60
REPORT_CATEGORY_MAX = 40  # what the hazard or need is, e.g. "Flooded road", "Trapped"
REPORT_PEOPLE_MAX = 999  # help requests: how many people need help

# ---- Limits on the public report endpoints (no accounts: phone ID + IP) ----
# One report of each kind per phone every this many seconds...
REPORT_PHONE_COOLDOWN_SECONDS = int(_number("REPORT_PHONE_COOLDOWN_SECONDS", 30))
# ...at most this many reports per phone in the window below...
REPORT_PHONE_MAX = int(_number("REPORT_PHONE_MAX", 6))
# ...and at most this many per IP (higher: many phones can share one IP).
REPORT_IP_MAX = int(_number("REPORT_IP_MAX", 30))
REPORT_WINDOW_SECONDS = int(_number("REPORT_WINDOW_SECONDS", 3600))
# Reading "my reports" and nearby hazards: at most this many requests per IP and per phone per window.
REPORT_READ_MAX = int(_number("REPORT_READ_MAX", 60))
REPORT_READ_WINDOW_SECONDS = int(_number("REPORT_READ_WINDOW_SECONDS", 60))

# ---- Weather (redesign part 4) ----
# Open-Meteo needs no key. The point is the middle of Batangas City.
WEATHER_LOCATION_NAME = os.getenv("WEATHER_LOCATION_NAME", "Batangas City")
WEATHER_LATITUDE = _number("WEATHER_LATITUDE", 13.7565)
WEATHER_LONGITUDE = _number("WEATHER_LONGITUDE", 121.0583)
# A forecast this young is served again without asking Open-Meteo.
WEATHER_CACHE_MINUTES = _number("WEATHER_CACHE_MINUTES", 10)
# Give up on Open-Meteo after this many seconds (then the last good forecast is served).
WEATHER_TIMEOUT_SECONDS = _number("WEATHER_TIMEOUT_SECONDS", 8)
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast")

# ---- Advisories and emergency numbers (redesign part 4) ----
# Only these sources count as "official" on first start. After that the list lives in the
# database (table advisory_sources) and an Admin edits it; changing this tuple later
# changes nothing on a database that already has a list.
DEFAULT_OFFICIAL_SOURCES = ("PAGASA", "NDRRMC", "Batangas City CDRRMO")
ADVISORY_TITLE_MAX = 120
ADVISORY_DETAILS_MAX = 1000
ADVISORY_SOURCE_MAX = 80
ADVISORY_URL_MAX = 500
EMERGENCY_NAME_MAX = 80
EMERGENCY_NUMBER_MAX = 30
EMERGENCY_DESCRIPTION_MAX = 140
# Only 911 is filled in until the Batangas City CDRRMO confirms the others.
DEFAULT_EMERGENCY_NUMBERS = (("911", "National Emergency"),)
# What an emergency number is for. The hotline sheet filters on these. A number with no tag is general.
EMERGENCY_CATEGORIES = ("medical", "accident", "flood", "violence", "missing_person")
SETTING_EMAIL_MAX = 120  # support email
# "Today" in the Admin's Me screen ("handled N reports today") starts at local midnight. The Philippines has
# no daylight saving, so a fixed offset from UTC is enough (and needs no time zone database on Windows).
ADMIN_DAY_UTC_OFFSET_HOURS = _number("ADMIN_DAY_UTC_OFFSET_HOURS", 8)

# ---- Chatbot (redesign part 4: placeholder, no AI connected) ----
# Which provider answers. "placeholder" is the only one built. An unknown name falls back to
# the placeholder with one warning in the log (see chat_service.py).
CHAT_PROVIDER = (os.getenv("CHAT_PROVIDER") or "placeholder").strip().lower()
# Longest question accepted (characters). The chat box on the site counts to 200 too.
CHAT_MAX_QUESTION_LENGTH = int(_number("CHAT_MAX_QUESTION_LENGTH", 200))
# Per-IP limit on POST /api/chat: at most this many questions in the window.
CHAT_IP_MAX_QUESTIONS = int(_number("CHAT_IP_MAX_QUESTIONS", 15))
CHAT_IP_WINDOW_SECONDS = int(_number("CHAT_IP_WINDOW_SECONDS", 600))
# For the future provider call: give up after this many seconds. Not used by the placeholder.
CHAT_TIMEOUT_SECONDS = _number("CHAT_TIMEOUT_SECONDS", 15)
# After a failed weather call, wait this many seconds before asking Open-Meteo again.
WEATHER_RETRY_SECONDS = _number("WEATHER_RETRY_SECONDS", 30)

# ---- Operations (redesign part 5) ----
# A phone blocked after too many false reports is unblocked automatically after this many days.
# 0 (the default) means a block never expires; an Admin can still unblock a phone by hand.
BLOCK_EXPIRES_DAYS = int(_number("BLOCK_EXPIRES_DAYS", 0))

# While the server runs, one background task purges old reports, removed centers, rejected places,
# expired sessions and expired phone blocks every this many minutes. 0 turns it off (the same
# purges still run once at startup, and by the scripts in backend/scripts).
PURGE_INTERVAL_MINUTES = int(_number("PURGE_INTERVAL_MINUTES", 60))

# Changing your password: wrong "current password" tries are limited per person and per IP, so the
# form cannot be used to guess a password. Counted over the window below.
PASSWORD_CHANGE_MAX_WRONG = int(_number("PASSWORD_CHANGE_MAX_WRONG", 5))
PASSWORD_CHANGE_IP_MAX_WRONG = int(_number("PASSWORD_CHANGE_IP_MAX_WRONG", 20))
PASSWORD_CHANGE_WINDOW_SECONDS = int(_number("PASSWORD_CHANGE_WINDOW_SECONDS", 600))
