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
