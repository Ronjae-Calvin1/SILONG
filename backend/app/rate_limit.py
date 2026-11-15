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


class ActionRateLimiter:
    """
    Sliding window per IP for add / remove / restore of evacuation centers:
    at most MANAGE_MAX_ACTIONS in MANAGE_WINDOW_SECONDS (config.py), shared by
    the three actions. Same limits as UpdateRateLimiter (memory only, per
    process, an IP behind a proxy looks shared).
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, ip: str) -> Optional[int]:
        """None if allowed (and recorded), otherwise the seconds to wait."""
        now = self._clock()
        with self._lock:
            hits = self._hits[ip]
            while hits and now - hits[0] > config.MANAGE_WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= config.MANAGE_MAX_ACTIONS:
                return max(1, int(config.MANAGE_WINDOW_SECONDS - (now - hits[0]) + 0.999))
            hits.append(now)
            # Drop IPs that have gone quiet so the dict cannot grow forever.
            for other in [k for k, q in self._hits.items() if k != ip and now - q[-1] > config.MANAGE_WINDOW_SECONDS]:
                del self._hits[other]
            return None


manage_limiter = ActionRateLimiter()


class SignInRateLimiter:
    """
    Sliding window per IP for sign-in attempts (any account, right or wrong):
    at most SIGNIN_IP_MAX_ATTEMPTS in SIGNIN_IP_WINDOW_SECONDS (config.py).
    Same limits as the others (memory only, per process, an IP behind a proxy
    looks shared). The per-account lock lives in accounts.py.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, ip: str) -> Optional[int]:
        """None if allowed (and recorded), otherwise the seconds to wait."""
        now = self._clock()
        with self._lock:
            hits = self._hits[ip]
            while hits and now - hits[0] > config.SIGNIN_IP_WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= config.SIGNIN_IP_MAX_ATTEMPTS:
                return max(1, int(config.SIGNIN_IP_WINDOW_SECONDS - (now - hits[0]) + 0.999))
            hits.append(now)
            for other in [k for k, q in self._hits.items() if k != ip and now - q[-1] > config.SIGNIN_IP_WINDOW_SECONDS]:
                del self._hits[other]
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


signin_limiter = SignInRateLimiter()


class ReportRateLimiter:
    """
    Limits for sending a report (help request or hazard), by phone ID and by IP.
    All numbers are in config.py.

      1. Cooldown: one report of each kind per phone every REPORT_PHONE_COOLDOWN_SECONDS.
      2. At most REPORT_PHONE_MAX reports per phone in REPORT_WINDOW_SECONDS.
      3. At most REPORT_IP_MAX reports per IP in the same window (higher than the
         phone limit, because many phones can share one IP on a mobile network).

    Same limits as the other limiters: memory only, per process, an IP behind a
    proxy looks shared. The phone ID is a random value from the browser, so a
    person can get a new one by clearing browser data; the IP limit is what
    holds then.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._last_for_kind: dict[Tuple[str, str], float] = {}
        self._phone_hits: dict[str, deque] = defaultdict(deque)
        self._ip_hits: dict[str, deque] = defaultdict(deque)

    def check(self, ip: str, phone: str, kind: str) -> Optional[Tuple[str, int]]:
        """None if allowed (and recorded), otherwise (\"cooldown\" | \"phone\" | \"ip\", seconds_to_wait)."""
        now = self._clock()
        window = config.REPORT_WINDOW_SECONDS
        with self._lock:
            self._prune(now)

            last = self._last_for_kind.get((phone, kind))
            if last is not None:
                wait = config.REPORT_PHONE_COOLDOWN_SECONDS - (now - last)
                if wait > 0:
                    return "cooldown", max(1, int(wait + 0.999))

            phone_hits = self._phone_hits[phone]
            if len(phone_hits) >= config.REPORT_PHONE_MAX:
                return "phone", max(1, int(window - (now - phone_hits[0]) + 0.999))

            ip_hits = self._ip_hits[ip]
            if len(ip_hits) >= config.REPORT_IP_MAX:
                return "ip", max(1, int(window - (now - ip_hits[0]) + 0.999))

            self._last_for_kind[(phone, kind)] = now
            phone_hits.append(now)
            ip_hits.append(now)
            return None

    def _prune(self, now: float) -> None:
        window = config.REPORT_WINDOW_SECONDS
        for key in [k for k, t in self._last_for_kind.items() if now - t > config.REPORT_PHONE_COOLDOWN_SECONDS]:
            del self._last_for_kind[key]
        for hits in (self._phone_hits, self._ip_hits):
            for key in list(hits):
                q = hits[key]
                while q and now - q[0] > window:
                    q.popleft()
                if not q:
                    del hits[key]

    def reset(self) -> None:
        with self._lock:
            self._last_for_kind.clear()
            self._phone_hits.clear()
            self._ip_hits.clear()


report_limiter = ReportRateLimiter()


class ReportReadLimiter:
    """
    Sliding window for reading "my reports" and nearby hazards: at most
    REPORT_READ_MAX requests per IP and per phone in REPORT_READ_WINDOW_SECONDS.
    A screen that refreshes every 10 seconds uses 6 a minute, well inside it.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, ip: str, phone: Optional[str] = None) -> Optional[int]:
        """None if allowed (and recorded), otherwise the seconds to wait."""
        now = self._clock()
        window = config.REPORT_READ_WINDOW_SECONDS
        keys = [f"ip:{ip}"] + ([f"phone:{phone}"] if phone else [])
        with self._lock:
            for key in list(self._hits):
                q = self._hits[key]
                while q and now - q[0] > window:
                    q.popleft()
                if not q:
                    del self._hits[key]
            for key in keys:
                q = self._hits[key]
                if len(q) >= config.REPORT_READ_MAX:
                    return max(1, int(window - (now - q[0]) + 0.999))
            for key in keys:
                self._hits[key].append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


read_limiter = ReportReadLimiter()
