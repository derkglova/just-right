import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from planner import estimate_demand, plan_item, target_level  # noqa: E402


def history(item_id, rows):
    return [{"date": f"2026-10-{i + 1:02d}", "item": item_id, **r} for i, r in enumerate(rows)]


class TestPlanner(unittest.TestCase):
    def test_target_level_croissant(self):
        # RM8 price, RM2 cost -> aim to have enough 75% of days
        self.assertAlmostEqual(target_level(8, 2), 0.75)

    def test_sold_out_demand_is_scaled_up(self):
        row = {"sold": 40, "leftover": 0, "sold_out_bucket": "12_2"}
        self.assertGreater(estimate_demand(row), 40)

    def test_leftover_day_uses_sales(self):
        row = {"sold": 30, "leftover": 10, "sold_out_bucket": None}
        self.assertEqual(estimate_demand(row), 30)

    def test_bakes_more_when_it_keeps_selling_out(self):
        item = {"id": "c", "name": "C", "price": 8, "cost": 2, "usual_batch": 40}
        rows = history("c", [{"baked": 40, "sold": 40, "leftover": 0, "sold_out_bucket": "12_2"}] * 14)
        self.assertGreater(plan_item(item, rows).quantity, 40)

    def test_bakes_less_with_steady_leftovers(self):
        item = {"id": "s", "name": "S", "price": 18, "cost": 6, "usual_batch": 15}
        rows = history("s", [{"baked": 15, "sold": 10, "leftover": 5, "sold_out_bucket": None}] * 14)
        self.assertLess(plan_item(item, rows).quantity, 15)

    def test_change_is_capped(self):
        item = {"id": "s", "name": "S", "price": 18, "cost": 6, "usual_batch": 20}
        rows = history("s", [{"baked": 20, "sold": 2, "leftover": 18, "sold_out_bucket": None}] * 14)
        self.assertGreaterEqual(plan_item(item, rows).quantity, 17)  # at most -15%

    def test_short_history_keeps_usual(self):
        item = {"id": "m", "name": "M", "price": 6, "cost": 2, "usual_batch": 24}
        rows = history("m", [{"baked": 24, "sold": 20, "leftover": 4, "sold_out_bucket": None}] * 3)
        self.assertEqual(plan_item(item, rows).quantity, 24)


if __name__ == "__main__":
    unittest.main()
