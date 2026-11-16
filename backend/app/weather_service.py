"""
Weather for Batangas City from Open-Meteo (free, no API key).

How it behaves:
  - A forecast younger than WEATHER_CACHE_MINUTES (config.py) is served again without a new call.
  - If the call fails (no internet, Open-Meteo down, a reply we cannot read), the LAST GOOD
    forecast is served with `is_stale: true` and the time it was received (`fetched_at`).
    The last good forecast is also kept in the database (cached_responses), so it survives a restart.
  - If there has never been a good forecast, the caller gets a plain-language 503. Numbers are never
    made up: a reply with a missing value is treated as a failed call, not filled in with zeros.
  - After a failed call the service waits WEATHER_RETRY_SECONDS before asking again, so a dead
    connection does not make every visitor wait for the timeout.

The ONLY network call is `_http_get_json`. The tests replace it; they never call the real service.
Standard library only (no new dependency).
"""
import json
import logging
import math
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import config
from .content_schemas import WeatherCurrentOut, WeatherDayOut, WeatherOut, WeatherStripOut
from .models import CachedResponse

log = logging.getLogger("silong.weather")

CACHE_KEY = "weather:current"
CACHE_KIND = "weather"
FORECAST_DAYS = 5
PH_TIME = timezone(timedelta(hours=8))  # Philippine time has no daylight saving, so a fixed offset is exact

# WMO weather codes used by Open-Meteo, in plain words.
_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light rain showers", 81: "Rain showers", 82: "Heavy rain showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


def describe(code: int) -> str:
    return _CODES.get(code, "Conditions not available")


# ---------------------------------------------------------------- the one network call

def _forecast_url() -> str:
    query = urllib.parse.urlencode({
        "latitude": config.WEATHER_LATITUDE,
        "longitude": config.WEATHER_LONGITUDE,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_gusts_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
        "wind_speed_unit": "kmh",
        "timezone": "Asia/Manila",
        "forecast_days": FORECAST_DAYS,
    })
    return f"{config.WEATHER_API_URL}?{query}"


def _http_get_json(url: str, timeout: float) -> Dict[str, Any]:
    """Ask Open-Meteo. The only place in this module that touches the network."""
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SILONG/1.0 (Batangas City emergency site)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https URL from config)
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------- reading the reply

def _num(value: Any, what: str, required: bool = True) -> Optional[float]:
    if value is None:
        if required:
            raise ValueError(f"missing {what}")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"bad {what}")
    return float(value)


def _parse(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Open-Meteo reply -> the small forecast we keep. Raises ValueError when something needed is missing."""
    cur = raw["current"]
    current = {
        "temperature_c": _num(cur.get("temperature_2m"), "temperature"),
        "feels_like_c": _num(cur.get("apparent_temperature"), "feels like", required=False),
        "humidity_percent": _num(cur.get("relative_humidity_2m"), "humidity", required=False),
        "wind_kph": _num(cur.get("wind_speed_10m"), "wind"),
        "wind_gust_kph": _num(cur.get("wind_gusts_10m"), "gusts", required=False),
        "rain_mm": _num(cur.get("precipitation"), "rain"),
        "weather_code": int(_num(cur.get("weather_code"), "weather code")),
        "is_day": None if cur.get("is_day") is None else bool(cur["is_day"]),
    }
    daily: List[Dict[str, Any]] = []
    d = raw.get("daily") or {}
    dates = d.get("time") or []

    def at(name: str, i: int):
        values = d.get(name) or []
        return values[i] if i < len(values) else None

    for i, date in enumerate(dates):
        try:
            daily.append({
                "date": str(date),
                "temp_max_c": _num(at("temperature_2m_max", i), "high"),
                "temp_min_c": _num(at("temperature_2m_min", i), "low"),
                "rain_mm": _num(at("precipitation_sum", i), "daily rain"),
                "rain_chance_percent": _num(at("precipitation_probability_max", i), "rain chance", required=False),
                "wind_max_kph": _num(at("wind_speed_10m_max", i), "daily wind", required=False),
                "weather_code": int(_num(at("weather_code", i), "daily weather code")),
            })
        except ValueError:
            continue  # a day with a missing number is left out, never filled in
    return {"current": current, "daily": daily}


# ---------------------------------------------------------------- cache

_lock = threading.Lock()
_last_good: Optional[Dict[str, Any]] = None  # {"fetched_at": datetime (naive UTC), "forecast": {...}}
_last_failure_at: Optional[datetime] = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reset() -> None:
    """Forget the in-memory forecast and failure (for tests). The database copy is not touched."""
    global _last_good, _last_failure_at
    with _lock:
        _last_good, _last_failure_at = None, None


def _load_saved(db: Session) -> Optional[Dict[str, Any]]:
    row = db.query(CachedResponse).filter(CachedResponse.key == CACHE_KEY).first()
    if row is None:
        return None
    try:
        saved = json.loads(row.content)
        return {"fetched_at": datetime.fromisoformat(saved["fetched_at"]), "forecast": saved["forecast"]}
    except (ValueError, KeyError, TypeError):
        return None  # unreadable copy: treated as no copy, never shown


def _save(db: Session, fetched_at: datetime, forecast: Dict[str, Any]) -> None:
    content = json.dumps({"fetched_at": fetched_at.isoformat(), "forecast": forecast})
    row = db.query(CachedResponse).filter(CachedResponse.key == CACHE_KEY).first()
    if row is None:
        db.add(CachedResponse(key=CACHE_KEY, kind=CACHE_KIND, content=content))
    else:
        row.content = content
    db.commit()


# ---------------------------------------------------------------- output

def _ph_text(dt_utc: datetime) -> str:
    local = dt_utc.replace(tzinfo=timezone.utc).astimezone(PH_TIME)
    hour = local.hour % 12 or 12
    return f"{local:%b} {local.day}, {hour}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def _render(entry: Dict[str, Any], stale: bool) -> WeatherOut:
    fc = entry["forecast"]
    cur = dict(fc["current"])
    current = WeatherCurrentOut(**cur, condition=describe(cur["weather_code"]))
    daily = [WeatherDayOut(**day, condition=describe(day["weather_code"])) for day in fc["daily"]]
    where = config.WEATHER_LOCATION_NAME
    return WeatherOut(
        location=where, latitude=config.WEATHER_LATITUDE, longitude=config.WEATHER_LONGITUDE,
        current=current, daily=daily, cyclone=None,
        fetched_at=entry["fetched_at"].replace(tzinfo=timezone.utc), is_stale=stale,
        notice=(
            f"We could not get a new forecast. This is the last one we received, on {_ph_text(entry['fetched_at'])}. "
            "Check PAGASA for the latest."
        ) if stale else None,
        strip=WeatherStripOut(
            headline=f"{round(current.temperature_c)}°C · {current.condition}",
            detail=f"{'Old forecast · ' if stale else ''}Tap to open alerts · {where}",
        ),
    )


def get_weather(db: Session) -> WeatherOut:
    """The forecast for Batangas City. See the top of this file for the rules."""
    global _last_good, _last_failure_at
    with _lock:
        now = _now()
        if _last_good is None:
            _last_good = _load_saved(db)  # after a restart
        entry = _last_good

        if entry is not None and now - entry["fetched_at"] < timedelta(minutes=config.WEATHER_CACHE_MINUTES):
            return _render(entry, stale=False)

        recently_failed = _last_failure_at is not None and (now - _last_failure_at) < timedelta(seconds=config.WEATHER_RETRY_SECONDS)
        if not recently_failed:
            try:
                forecast = _parse(_http_get_json(_forecast_url(), config.WEATHER_TIMEOUT_SECONDS))
                _last_good = {"fetched_at": now, "forecast": forecast}
                _last_failure_at = None
                try:
                    _save(db, now, forecast)
                except Exception:  # noqa: BLE001  (keeping a copy is best effort; the forecast is good)
                    db.rollback()
                    log.warning("Could not keep a copy of the forecast in the database.")
                return _render(_last_good, stale=False)
            except Exception as e:  # noqa: BLE001  (any failure means: use the last good forecast)
                _last_failure_at = now
                log.warning("Weather call failed (%s). Using the last good forecast if there is one.", type(e).__name__)

        if entry is not None:
            return _render(entry, stale=True)

    raise HTTPException(
        status_code=503,
        detail="We can't get the weather right now. Please try again in a few minutes, or check PAGASA for the latest.",
    )
