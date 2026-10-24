"""Daily weather for the shop (Cyberjaya), from Open-Meteo: free, no API key.

For each date we keep two numbers: rain (mm for the whole day) and the day's top temperature (°C).
Everything we fetch is cached in data/weather.json, so the app still works when the API is down.
If a day isn't known at all, we use a typical Cyberjaya day (no rain, 32 °C).
"""
import json
from datetime import date, timedelta

import requests

from planner import DATA_DIR

LATITUDE, LONGITUDE = 2.92, 101.65          # Cyberjaya
CACHE_FILE = DATA_DIR / "weather.json"
TYPICAL_DAY = {"rain": 0.0, "temp": 32.0}

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"   # past days (a few days behind)
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"          # last 2 weeks + next few days


def load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(dict(sorted(cache.items())), indent=1) + "\n")


def _fetch(url: str, **params) -> dict:
    """Ask Open-Meteo for daily rain + top temperature. Returns {date: {"rain", "temp"}}."""
    response = requests.get(url, timeout=10, params={
        "latitude": LATITUDE, "longitude": LONGITUDE, "timezone": "Asia/Kuala_Lumpur",
        "daily": "precipitation_sum,temperature_2m_max", **params,
    })
    response.raise_for_status()
    daily = response.json()["daily"]
    days = {}
    for day, rain, temp in zip(daily["time"], daily["precipitation_sum"], daily["temperature_2m_max"]):
        if rain is not None and temp is not None:
            days[day] = {"rain": round(rain, 1), "temp": round(temp, 1)}
    return days


def history(start: date, end: date) -> dict:
    """Weather for every day from start to end (fetched once, then cached)."""
    cache = load_cache()
    wanted = [(start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)]
    if any(day not in cache for day in wanted):
        try:
            cache.update(_fetch(ARCHIVE_URL, start_date=start.isoformat(), end_date=end.isoformat()))
            # The archive is a few days behind; the forecast API covers the last two weeks.
            cache.update(_fetch(FORECAST_URL, past_days=14, forecast_days=1))
            save_cache(cache)
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"Weather history not available ({e}); using cached or typical days.")
    return {day: cache.get(day, TYPICAL_DAY) for day in wanted}


def for_day(day: date) -> dict:
    """Weather for one day: the forecast for today/tomorrow, the record for past days."""
    key = day.isoformat()
    cache = load_cache()
    if key in cache and day < date.today():
        return cache[key]   # past days don't change
    try:
        cache.update(_fetch(FORECAST_URL, past_days=14, forecast_days=3))
        save_cache(cache)
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"Weather forecast not available ({e}); using cached or typical day.")
    return cache.get(key, TYPICAL_DAY)
