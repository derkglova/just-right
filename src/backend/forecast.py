"""AI demand forecast: how many of each item customers will want on a given day.

One scikit-learn LinearRegression per item, trained on every day of sales history.
Inputs (features): day of the week, rain (mm), top temperature (°C).
Target: demand = sales, scaled up on sold-out days (planner.estimate_demand).

Why linear: it's easy to explain. The model learns one number per input, e.g.
"Saturday: +6 croissants", "each mm of rain: -0.3", so every prediction can be split
into "a usual day + Saturday + rain" and shown to the manager as the reason.

It retrains from scratch each time a plan is made (it takes milliseconds), so every new
closing count is learned straight away. One-off event days (marked by the manager) count
5x less, so a big order doesn't make normal days look busier.

backtest() checks the model honestly: for each past day it trains only on the days before,
predicts that day, and compares with what really sold, next to the old 28-day average.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sqrt
from statistics import mean

from sklearn.linear_model import LinearRegression

from planner import EVENT_WEIGHT, HISTORY_DAYS, estimate_demand

MIN_DAYS = 21          # fewer days than this: not enough to learn from, use the plain average
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TYPICAL_DAY = {"rain": 0.0, "temp": 32.0}


def features(day: date, w: dict) -> list:
    """[Tue, Wed, Thu, Fri, Sat, Sun, rain, temp]. Monday is the 'all zeros' day."""
    return [1.0 if day.weekday() == d else 0.0 for d in range(1, 7)] + [w["rain"], w["temp"]]


@dataclass
class ItemModel:
    model: LinearRegression
    means: list        # average of each input over the training days (the "usual day")
    error: float       # typical miss in pieces (weighted root-mean-square error)
    days: int


def train_item(rows: list, weather_by_date: dict, event_dates=()) -> ItemModel | None:
    if len(rows) < MIN_DAYS:
        return None
    X = [features(date.fromisoformat(r["date"]), weather_by_date.get(r["date"], TYPICAL_DAY)) for r in rows]
    y = [estimate_demand(r) for r in rows]
    w = [EVENT_WEIGHT if r["date"] in event_dates else 1.0 for r in rows]
    model = LinearRegression().fit(X, y, sample_weight=w)
    misses = [(actual - predicted) ** 2 * weight for actual, predicted, weight in zip(y, model.predict(X), w)]
    error = sqrt(sum(misses) / sum(w))
    means = [mean(column) for column in zip(*X)]
    return ItemModel(model, means, error, len(rows))


def explain(m: ItemModel, day: date, w: dict) -> dict:
    """Prediction for one day, split into parts: usual day + weekday + rain + temperature."""
    x = features(day, w)
    parts = [float(c * (xi - mi)) for c, xi, mi in zip(m.model.coef_, x, m.means)]
    usual = float(m.model.predict([m.means])[0])
    rain_label = "rain" if w["rain"] >= 1 else "dry"
    return {
        "demand": max(0.0, usual + sum(parts)),
        "error": float(m.error),
        "usual": usual,
        "parts": [(DAY_NAMES[day.weekday()], sum(parts[:6])), (rain_label, parts[6]), ("heat", parts[7])],
        "days": m.days,
    }


def rows_by_item(history: list) -> dict:
    by_item = {}
    for r in sorted(history, key=lambda r: r["date"]):
        by_item.setdefault(r["item"], []).append(r)
    return by_item


def predictions_for(items: list, history: list, day: date, weather_by_date: dict,
                    day_weather: dict, event_dates=()) -> dict:
    """{item_id: explain(...)} for every item with enough history."""
    by_item = rows_by_item(history)
    out = {}
    for item in items:
        m = train_item(by_item.get(item["id"], []), weather_by_date, event_dates)
        if m:
            out[item["id"]] = explain(m, day, day_weather)
    return out


def learned_effects(items: list, history: list, weather_by_date: dict, event_dates=()) -> list:
    """What the model learned, per item: weekday effects vs an average day, rain per 10 mm, heat per °C."""
    by_item = rows_by_item(history)
    out = []
    for item in items:
        m = train_item(by_item.get(item["id"], []), weather_by_date, event_dates)
        if not m:
            continue
        weekday = [0.0] + [float(c) for c in m.model.coef_[:6]]   # Monday is 0 by definition
        avg = mean(weekday)
        out.append({
            "item": item["name"],
            "weekday": {DAY_NAMES[d][:3]: round(weekday[d] - avg, 1) for d in range(7)},
            "rain_10mm": round(float(m.model.coef_[6]) * 10, 1),
            "temp_1c": round(float(m.model.coef_[7]), 1),
            "error": round(float(m.error), 1),
            "days": m.days,
        })
    return out


def backtest(items: list, history: list, weather_by_date: dict, event_dates=()) -> list:
    """For each past day: train on earlier days only, predict that day, compare with what sold.
    Returns [{date, ai, old}] with the average miss in pieces per item (event days skipped)."""
    by_item = rows_by_item(history)
    dates = sorted({r["date"] for r in history})
    results = []
    for day in dates[MIN_DAYS:]:
        if day in event_dates:
            continue
        ai_miss, old_miss = [], []
        for item in items:
            rows = by_item.get(item["id"], [])
            before = [r for r in rows if r["date"] < day]
            today = next((r for r in rows if r["date"] == day), None)
            m = train_item(before, weather_by_date, event_dates)
            if not today or not m:
                continue
            actual = estimate_demand(today)
            predicted = explain(m, date.fromisoformat(day), weather_by_date.get(day, TYPICAL_DAY))["demand"]
            average = mean(estimate_demand(r) for r in before[-HISTORY_DAYS:])
            ai_miss.append(float(abs(actual - predicted)))
            old_miss.append(abs(actual - average))
        if ai_miss:
            results.append({"date": day, "ai": round(mean(ai_miss), 2), "old": round(mean(old_miss), 2)})
    return results

