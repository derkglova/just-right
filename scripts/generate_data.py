"""Generate synthetic sales history for the demo (simulated Orbyte POS data).

Run:  python scripts/generate_data.py
Writes src/backend/data/sales_history.json (and caches the weather in data/weather.json).

The sales are made up, but they follow patterns a real bakery has, so the AI forecast
has something to learn:
- weekends sell more (Saturday most),
- rainy days sell less (fewer people walk in),
- very hot days sell slightly less.
The weather is REAL past weather for Cyberjaya from Open-Meteo. Fixed seed, so the same every time.
"""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
sys.path.insert(0, str(BACKEND))
import weather  # noqa: E402

DATA_DIR = BACKEND / "data"
OPEN_HOUR, CLOSE_HOUR = 8, 18  # shop opens 8 AM, closes 6 PM
DAYS = 120
END_DATE = date(2026, 10, 22)  # last day of history (Thursday)

# True (hidden) customer demand per item on a normal dry weekday: (mean, spread).
# The shop always bakes its usual batch, so some days it sells out.
DEMAND = {
    "croissant": (42, 4),   # often more than the 40 baked, so it sells out (esp. weekends)
    "sourdough": (11, 2),   # usually less than the 15 baked, so leftovers
    "muffin": (21, 3),      # roughly right
}
WEEKDAY_EFFECT = [0.92, 0.95, 0.97, 1.00, 1.06, 1.22, 1.14]   # Mon .. Sun


def rain_effect(rain_mm: float) -> float:
    """Each mm of rain keeps a few customers away, up to 30% fewer on a very wet day."""
    return 1 - min(0.30, rain_mm * 0.02)


def heat_effect(temp: float) -> float:
    """Above 33 °C, 2% fewer per extra degree."""
    return 1 - max(0.0, temp - 33) * 0.02


def bucket_for(hour: float) -> str:
    if hour < 12:
        return "before_12"
    if hour < 14:
        return "12_2"
    if hour < 16:
        return "2_4"
    return "after_4"


def main() -> None:
    random.seed(42)
    items = {i["id"]: i for i in json.loads((DATA_DIR / "items.json").read_text())}
    start = END_DATE - timedelta(days=DAYS - 1)
    days_weather = weather.history(start, END_DATE)
    rows = []
    for d in range(DAYS):
        day = start + timedelta(days=d)
        w = days_weather[day.isoformat()]
        effect = WEEKDAY_EFFECT[day.weekday()] * rain_effect(w["rain"]) * heat_effect(w["temp"])
        for item_id, (mean, sd) in DEMAND.items():
            baked = items[item_id]["usual_batch"]
            demand = max(0, round(random.gauss(mean * effect, sd)))
            sold = min(baked, demand)
            leftover = baked - sold
            row = {"date": day.isoformat(), "item": item_id, "baked": baked,
                   "sold": sold, "leftover": leftover, "sold_out_bucket": None}
            if leftover == 0 and demand > baked:
                # Assume steady sales: it ran out after this share of the day.
                share = baked / demand
                hour = OPEN_HOUR + (CLOSE_HOUR - OPEN_HOUR) * share
                row["sold_out_bucket"] = bucket_for(hour)
            rows.append(row)
    (DATA_DIR / "sales_history.json").write_text(json.dumps(rows, indent=2))
    print(f"Wrote {len(rows)} rows ({DAYS} days) to {DATA_DIR / 'sales_history.json'}")


if __name__ == "__main__":
    main()
