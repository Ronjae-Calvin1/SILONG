"""
Scheduled cleanup while the server runs (redesign part 5).

Until now these purges ran only at startup or by script. One background task now runs them every
config.PURGE_INTERVAL_MINUTES (default 60; 0 turns it off):

    reports          help requests and hazard reports older than REPORTS_KEEP_DAYS
    removed_places   removed centers and rejected places older than REMOVED_CENTERS_KEEP_DAYS
    sessions         sign-ins unused for longer than STAFF_IDLE_MINUTES
    phone_blocks     phone blocks older than BLOCK_EXPIRES_DAYS (when that is not 0)

Each job gets its own database session, and one job failing never stops the others or the loop.
The log gets the job name and the counts only, never any data (for an error: the job name and the
kind of error, not its message). The loop starts and stops with the server (main.py, lifespan).
Each server process runs its own copy; the purges are safe to run twice at once.
"""
import asyncio
import logging
from typing import Callable, Dict, List, Optional, Tuple

from . import accounts, config, place_service, report_service
from .database import SessionLocal

log = logging.getLogger("silong.maintenance")

# (name, function(db) -> how many it deleted or lifted). Tests replace entries to simulate a failure.
JOBS: List[Tuple[str, Callable]] = [
    ("reports", report_service.purge_old_reports),
    ("removed_places", place_service.purge_removed_centers),
    ("sessions", accounts.purge_idle_sessions),
    ("phone_blocks", report_service.lift_expired_blocks),
]


def run_jobs() -> Dict[str, Optional[int]]:
    """Runs every job once. Returns {job name: count}, with None for a job that failed."""
    results: Dict[str, Optional[int]] = {}
    for name, job in list(JOBS):
        db = SessionLocal()
        try:
            count = job(db)
            results[name] = count
            if count:
                log.info("Cleanup job %s: %s item(s).", name, count)
        except Exception as e:  # noqa: BLE001 - one failing job must not stop the others
            db.rollback()
            results[name] = None
            log.error("Cleanup job %s failed (%s).", name, type(e).__name__)  # no message, no traceback: they can hold data
        finally:
            db.close()
    return results


class Scheduler:
    """The background loop. start() and stop() are called by the server's startup and shutdown."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop: Optional[asyncio.Event] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, interval_seconds: Optional[float] = None) -> bool:
        """Starts the loop. Does nothing (False) when the interval is 0. `interval_seconds` is for tests."""
        interval = config.PURGE_INTERVAL_MINUTES * 60 if interval_seconds is None else interval_seconds
        if interval <= 0 or self.running:
            return False
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop(interval, self._stop))
        return True

    async def stop(self) -> None:
        """Ends the loop and waits for a job that is running to finish."""
        if self._task is None:
            return
        self._stop.set()
        try:
            await self._task
        finally:
            self._task, self._stop = None, None

    async def _loop(self, interval: float, stop: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return  # asked to stop
            except asyncio.TimeoutError:
                pass
            try:
                await asyncio.to_thread(run_jobs)
            except Exception as e:  # noqa: BLE001 - the loop itself must survive anything
                log.error("Cleanup run failed (%s).", type(e).__name__)


scheduler = Scheduler()
