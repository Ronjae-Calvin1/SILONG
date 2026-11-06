"""
Tiny in-memory rate limiter for status updates (there are no accounts, so the
client IP is the only handle we have).

Two rules, both configured in config.py:
  1. One update per place per IP every STATUS_COOLDOWN_SECONDS.
  2. At most STATUS_IP_MAX_UPDATES updates per IP in STATUS_IP_WINDOW_SECONDS.

Limits of this approach (fine for now, worth knowing):
  - Memory only: counters reset when the server restarts, and each worker
    process keeps its own counters.
  - Behind a reverse proxy every visitor can look like the same IP. If the site
    is deployed behind one, pass the real client IP in from the proxy.
  - It slows casual spam down. It does not stop a determined attacker.
"""
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Optional, Tuple

from . import config


class UpdateRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._last_for_place: dict[Tuple[str, int], float] = {}
        self._recent_for_ip: dict[str, deque] = defaultdict(deque)

    def check(self, ip: str, facility_id: int) -> Optional[Tuple[str, int]]:
        """
        Returns None if the update is allowed (and records it), otherwise
        ("place" | "ip", seconds_to_wait).
        """
        now = self._clock()
        with self._lock:
            self._prune(now)

            last = self._last_for_place.get((ip, facility_id))
            if last is not None:
                wait = config.STATUS_COOLDOWN_SECONDS - (now - last)
                if wait > 0:
                    return "place", max(1, int(wait + 0.999))

            recent = self._recent_for_ip[ip]
            if len(recent) >= config.STATUS_IP_MAX_UPDATES:
                wait = config.STATUS_IP_WINDOW_SECONDS - (now - recent[0])
                return "ip", max(1, int(wait + 0.999))

            # Allowed: record it.
            self._last_for_place[(ip, facility_id)] = now
            recent.append(now)
            return None

    def _prune(self, now: float) -> None:
        """Forget old entries so memory cannot grow without bound."""
        for key in [k for k, t in self._last_for_place.items() if now - t > config.STATUS_COOLDOWN_SECONDS]:
            del self._last_for_place[key]
        for ip in list(self._recent_for_ip):
            q = self._recent_for_ip[ip]
            while q and now - q[0] > config.STATUS_IP_WINDOW_SECONDS:
                q.popleft()
            if not q:
                del self._recent_for_ip[ip]


limiter = UpdateRateLimiter()
