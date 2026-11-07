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
