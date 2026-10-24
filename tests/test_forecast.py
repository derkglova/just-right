import random
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "backend"))

import forecast  # noqa: E402
from planner import make_plan  # noqa: E402

ITEMS = [{"id": "croissant", "name": "Croissant", "price": 8.0, "cost": 2.0, "usual_batch": 60}]
START = date(2026, 6, 1)


def fake_history(days=120, saturday_boost=10, rain_per_mm=-1.0):
    """Demand 40, +10 on Saturdays, -1 per mm of rain. Batch 60, so it never sells out."""
    random.seed(1)
    history, weather = [], {}
    for n in range(days):
        day = START + timedelta(days=n)
        rain = random.choice([0, 0, 0, 5, 10])
        weather[day.isoformat()] = {"rain": rain, "temp": 32.0}
        sold = round(40 + (saturday_boost if day.weekday() == 5 else 0) + rain_per_mm * rain + random.gauss(0, 1))
        history.append({"date": day.isoformat(), "item": "croissant", "baked": 60, "sold": sold,
                        "leftover": 60 - sold, "sold_out_bucket": None})
    return history, weather


class TestForecast(unittest.TestCase):
    def test_learns_saturday_and_rain(self):
        history, weather = fake_history()
        effects = forecast.learned_effects(ITEMS, history, weather)[0]
        self.assertGreater(effects["weekday"]["Sat"], 6)        # Saturdays sell more
        self.assertAlmostEqual(effects["rain_10mm"], -10, delta=2)   # 10 mm of rain: about 10 fewer

    def test_prediction_parts_add_up(self):
        history, weather = fake_history()
        p = forecast.predictions_for(ITEMS, history, date(2026, 10, 3), weather, {"rain": 10, "temp": 32})["croissant"]
        self.assertAlmostEqual(p["usual"] + sum(v for _, v in p["parts"]), p["demand"], places=6)
        self.assertEqual(p["parts"][0][0], "Saturday")

    def test_not_enough_history_falls_back_to_average(self):
        history, weather = fake_history(days=10)
        self.assertEqual(forecast.predictions_for(ITEMS, history, date(2026, 6, 11), weather, {"rain": 0, "temp": 32}), {})
        rec = make_plan(ITEMS, history)[0]
        self.assertNotIn("Usual day", rec.reason)   # the old average reason

    def test_event_days_count_less(self):
        history, weather = fake_history()
        # Three Saturdays with a huge one-off order of +60
        big = [r for r in history if date.fromisoformat(r["date"]).weekday() == 5][-3:]
        for r in big:
            r["sold"] += 60
        events = {r["date"] for r in big}
        normal = forecast.learned_effects(ITEMS, history, weather)[0]["weekday"]["Sat"]
        toned_down = forecast.learned_effects(ITEMS, history, weather, events)[0]["weekday"]["Sat"]
        self.assertLess(toned_down, normal)

    def test_ai_beats_old_average_in_backtest(self):
        history, weather = fake_history()
        days = forecast.backtest(ITEMS, history, weather)
        ai = sum(d["ai"] for d in days) / len(days)
        old = sum(d["old"] for d in days) / len(days)
        self.assertLess(ai, old)


if __name__ == "__main__":
    unittest.main()
