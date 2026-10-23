"""Generate synthetic sales history for the demo (simulated Orbyte POS data).

Run:  python scripts/generate_data.py
Writes src/data/sales_history.json. Fixed seed, so the output is the same every time.
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "data"
OPEN_HOUR, CLOSE_HOUR = 8, 18  # shop opens 8 AM, closes 6 PM
DAYS = 28
END_DATE = date(2026, 10, 22)  # last day of history (Thursday)

# True (hidden) customer demand per item: (mean, spread). The shop bakes its usual batch.
DEMAND = {
    "croissant": (45, 5),   # usually more than the 40 baked, so it often sells out
    "sourdough": (11, 2),   # usually less than the 15 baked, so leftovers
    "muffin": (22, 3),      # roughly right
}


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
    rows = []
    for d in range(DAYS):
        day = END_DATE - timedelta(days=DAYS - 1 - d)
        weekend_boost = 1.12 if day.weekday() >= 5 else 1.0
        for item_id, (mean, sd) in DEMAND.items():
            baked = items[item_id]["usual_batch"]
            demand = max(0, round(random.gauss(mean * weekend_boost, sd)))
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
    print(f"Wrote {len(rows)} rows to {DATA_DIR / 'sales_history.json'}")


if __name__ == "__main__":
    main()
