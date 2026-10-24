"""Just Right planner: works out how many of each item to bake tomorrow.

Idea in one line: running out costs more than a leftover for most bakery items,
so aim for the *right* amount of waste, not zero (the newsvendor model).

Expected demand comes from the AI forecast (forecast.py: weekday + weather), or from the
28-day average when there isn't enough history. Then: quantity = demand + z x typical miss.

Run `python src/backend/planner.py` to print tomorrow's plan from the sample data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from math import sqrt
from statistics import NormalDist, mean

DATA_DIR = Path(__file__).resolve().parent / "data"

HISTORY_DAYS = 28        # how far back we look
MAX_CHANGE = 0.15        # never change more than ±15% from the usual batch in one go
EVENT_WEIGHT = 0.2       # a one-off event day counts as 1/5 of a normal day

# When an item sells out we never see the real demand. Estimate it by how early it ran out.
SOLD_OUT_UPLIFT = {
    "before_12": 1.35,
    "12_2": 1.20,
    "2_4": 1.10,
    "after_4": 1.03,
}


@dataclass
class Recommendation:
    item_id: str
    name: str
    usual: int
    quantity: int
    change: int
    target_level: float      # share of days we aim to have enough
    expected_demand: float
    reason: str


def estimate_demand(row: dict) -> float:
    """Demand for one day. If it sold out, sales understate demand, so scale up."""
    bucket = row.get("sold_out_bucket")
    if row["leftover"] == 0 and bucket:
        return row["sold"] * SOLD_OUT_UPLIFT.get(bucket, 1.0)
    return float(row["sold"])


def target_level(price: float, cost: float) -> float:
    """Newsvendor critical ratio: profit lost by running out vs cost of a leftover."""
    underage = price - cost   # profit lost when a customer can't buy one
    overage = cost            # ingredients lost when one is thrown away
    return underage / (underage + overage)


def plan_item(item: dict, history: list[dict], prediction: dict = None, event_dates=()) -> Recommendation:
    """prediction: the AI forecast for this item (forecast.explain), or None to use the
    28-day average. event_dates: one-off days that count less in the average."""
    rows = sorted((r for r in history if r["item"] == item["id"]), key=lambda r: r["date"])
    rows = rows[-HISTORY_DAYS:]
    usual = int(item["usual_batch"])
    level = target_level(item["price"], item["cost"])

    if len(rows) < 7:
        return Recommendation(item["id"], item["name"], usual, usual, 0, round(level, 2), float(usual),
                              "Not enough history yet. Keeping the usual batch.")

    if prediction:
        # AI forecast: expected demand and its typical miss.
        avg, spread = prediction["demand"], prediction["error"]
    else:
        # Plain average of the last 28 days (event days count 1/5).
        demands = [estimate_demand(r) for r in rows]
        weights = [EVENT_WEIGHT if r["date"] in event_dates else 1.0 for r in rows]
        avg = sum(d * w for d, w in zip(demands, weights)) / sum(weights)
        spread = sqrt(sum(w * (d - avg) ** 2 for d, w in zip(demands, weights)) / sum(weights))
    z = NormalDist().inv_cdf(level)
    raw = avg + z * spread

    low, high = usual * (1 - MAX_CHANGE), usual * (1 + MAX_CHANGE)
    quantity = int(round(min(max(raw, low), high)))

    if prediction:
        reason = _ai_reason(prediction, quantity, raw)
    else:
        last_week = rows[-7:]
        sold_outs = sum(1 for r in last_week if r["leftover"] == 0 and r.get("sold_out_bucket"))
        avg_left = mean(r["leftover"] for r in last_week)
        reason = _reason(quantity - usual, sold_outs, avg_left, level)

    return Recommendation(item["id"], item["name"], usual, quantity, quantity - usual,
                          round(level, 2), round(avg, 1), reason)


def _ai_reason(prediction: dict, quantity: int, raw: float) -> str:
    """Short why: expected sales, then what pushes it up or down vs a usual day (biggest first).
    e.g. "~33 sell · rain -7, Sunday +3". A few extra are baked on top (the newsvendor rule)."""
    parts = sorted(prediction["parts"], key=lambda part: -abs(part[1]))
    tags = [f"{label} {value:+.0f}" for label, value in parts if abs(value) >= 0.5]
    return f"~{prediction['demand']:.0f} sell · " + (", ".join(tags) if tags else "normal day")


def _reason(change: int, sold_outs: int, avg_left: float, level: float) -> str:
    margin = "high margin" if level >= 0.7 else "lower margin"
    if change > 0:
        return f"Sold out {sold_outs} of the last 7 days ({margin}, worth baking a few extra)."
    if change < 0:
        return f"About {avg_left:.0f} left over on average this week."
    return "About right. Keeping the usual batch."


def make_plan(items: list[dict], history: list[dict], predictions: dict = None,
              event_dates=()) -> list[Recommendation]:
    """predictions: {item_id: AI forecast} from forecast.py; items without one use the average."""
    predictions = predictions or {}
    return [plan_item(item, history, predictions.get(item["id"]), event_dates) for item in items]


def load_data(data_dir: Path = DATA_DIR) -> tuple[list[dict], list[dict]]:
    items = json.loads((data_dir / "items.json").read_text())
    history = json.loads((data_dir / "sales_history.json").read_text())
    return items, history


if __name__ == "__main__":
    from datetime import date, timedelta
    import forecast
    import weather

    items, history = load_data()
    day = date.fromisoformat(max(r["date"] for r in history)) + timedelta(days=1)
    day_weather = weather.for_day(day)
    predictions = forecast.predictions_for(items, history, day, weather.load_cache(), day_weather)
    plan = make_plan(items, history, predictions)
    print(f"Bake plan for {day} (sample data) · weather: {day_weather}\n")
    for rec in plan:
        sign = f"+{rec.change}" if rec.change > 0 else str(rec.change)
        print(f"{rec.name:<16} {rec.quantity:>3}  ({sign:>3} vs usual {rec.usual})  {rec.reason}")
    print("\nDetails:")
    for rec in plan:
        print(" ", asdict(rec))
