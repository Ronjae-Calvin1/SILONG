"""
Tunable settings for the capacity / availability feature.

Everything that is "still to be confirmed" with the project documentation
lives here, in one place. Each value can also be overridden with an
environment variable, which is handy for testing (for example
STATUS_COOLDOWN_SECONDS=0 turns the per-place cooldown off).
"""
import os
from datetime import timedelta


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

# Add / remove / restore share one allowance per IP.
MANAGE_MAX_ACTIONS = int(_number("MANAGE_MAX_ACTIONS", 10))
MANAGE_WINDOW_SECONDS = int(_number("MANAGE_WINDOW_SECONDS", 600))

# Salt for the hashed IPs in the action log. Set IP_HASH_SALT in the environment
# to keep hashes comparable across restarts. If it is not set, a random salt is
# made on each start (hashes still hide the IP; they just stop matching old ones).
IP_HASH_SALT = os.getenv("IP_HASH_SALT") or os.urandom(16).hex()

# ---- Staff accounts (Responder, Super admin) ----
# Staff sessions end after this many minutes without any request.
STAFF_IDLE_MINUTES = int(_number("STAFF_IDLE_MINUTES", 30))
# This many wrong passwords in a row lock the account...
SIGNIN_MAX_WRONG_TRIES = int(_number("SIGNIN_MAX_WRONG_TRIES", 5))
# ...for this many minutes. A Super admin can unlock it sooner.
SIGNIN_LOCK_MINUTES = int(_number("SIGNIN_LOCK_MINUTES", 15))

# Per-IP limit on sign-in attempts of any account (slows guessing across many
# names; the per-account lock above handles guessing one name).
SIGNIN_IP_MAX_ATTEMPTS = int(_number("SIGNIN_IP_MAX_ATTEMPTS", 20))
SIGNIN_IP_WINDOW_SECONDS = int(_number("SIGNIN_IP_WINDOW_SECONDS", 600))

# Shortest password a Super admin can give a new account (a typo guard, not a policy).
MIN_PASSWORD_LENGTH = int(_number("MIN_PASSWORD_LENGTH", 8))

# ---- Help requests and hazard reports (redesign part 2) ----
# Reports (both kinds) are deleted this many days after they were sent.
REPORTS_KEEP_DAYS = int(_number("REPORTS_KEEP_DAYS", 30))

# A hazard shows to the public as "Unconfirmed" once this many DIFFERENT phones
# reported it. A responder or Super admin can verify it sooner.
HAZARD_UNCONFIRMED_PHONES = int(_number("HAZARD_UNCONFIRMED_PHONES", 3))

# After this many reports marked false from one phone, that phone cannot send reports.
FALSE_REPORTS_BEFORE_BLOCK = int(_number("FALSE_REPORTS_BEFORE_BLOCK", 3))

# "Near me" range for hazard reports, in kilometres.
NEAR_ME_KM = _number("NEAR_ME_KM", 1)

# The responder screens poll about this often (seconds). Sent to the screen with every list.
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
