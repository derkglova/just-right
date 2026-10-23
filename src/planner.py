"""Just Right planner: works out how many of each item to bake tomorrow.

Idea in one line: running out costs more than a leftover for most bakery items,
so aim for the *right* amount of waste, not zero (the newsvendor model).

Run `python src/planner.py` to print tomorrow's plan from the sample data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import NormalDist, mean, pstdev

DATA_DIR = Path(__file__).resolve().parent / "data"

HISTORY_DAYS = 28        # how far back we look
MAX_CHANGE = 0.15        # never change more than ±15% from the usual batch in one go

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


def plan_item(item: dict, history: list[dict]) -> Recommendation:
    rows = sorted((r for r in history if r["item"] == item["id"]), key=lambda r: r["date"])
    rows = rows[-HISTORY_DAYS:]
    usual = int(item["usual_batch"])
    level = target_level(item["price"], item["cost"])

    if len(rows) < 7:
        return Recommendation(item["id"], item["name"], usual, usual, 0, round(level, 2), float(usual),
                              "Not enough history yet. Keeping the usual batch.")

    demands = [estimate_demand(r) for r in rows]
    avg, spread = mean(demands), pstdev(demands)
    z = NormalDist().inv_cdf(level)
    raw = avg + z * spread

    low, high = usual * (1 - MAX_CHANGE), usual * (1 + MAX_CHANGE)
    quantity = int(round(min(max(raw, low), high)))

    last_week = rows[-7:]
    sold_outs = sum(1 for r in last_week if r["leftover"] == 0 and r.get("sold_out_bucket"))
    avg_left = mean(r["leftover"] for r in last_week)
    reason = _reason(quantity - usual, sold_outs, avg_left, level)

    return Recommendation(item["id"], item["name"], usual, quantity, quantity - usual,
                          round(level, 2), round(avg, 1), reason)


def _reason(change: int, sold_outs: int, avg_left: float, level: float) -> str:
    margin = "high margin" if level >= 0.7 else "lower margin"
    if change > 0:
        return f"Sold out {sold_outs} of the last 7 days ({margin}, worth baking a few extra)."
    if change < 0:
        return f"About {avg_left:.0f} left over on average this week."
    return "About right. Keeping the usual batch."


def make_plan(items: list[dict], history: list[dict]) -> list[Recommendation]:
    return [plan_item(item, history) for item in items]


def load_data(data_dir: Path = DATA_DIR) -> tuple[list[dict], list[dict]]:
    items = json.loads((data_dir / "items.json").read_text())
    history = json.loads((data_dir / "sales_history.json").read_text())
    return items, history


if __name__ == "__main__":
    items, history = load_data()
    print("Tomorrow's bake plan (sample data)\n")
    for rec in make_plan(items, history):
        sign = f"+{rec.change}" if rec.change > 0 else str(rec.change)
        print(f"{rec.name:<16} {rec.quantity:>3}  ({sign:>3} vs usual {rec.usual})  {rec.reason}")
    print("\nDetails:")
    for rec in make_plan(items, history):
        print(" ", asdict(rec))
