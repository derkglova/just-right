import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "backend"))

import db  # noqa: E402
from planner import Recommendation  # noqa: E402


def rec(item_id, quantity):
    return Recommendation(item_id, item_id.title(), 40, quantity, quantity - 40, 0.75, 42.0, "Test reason")


class TestDb(unittest.TestCase):
    def setUp(self):
        # Use a fresh database file for every test, never the real one.
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init()

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_loads_sample_sales_once(self):
        count = len(db.sales_history())
        self.assertEqual(count, 84)
        db.init()
        self.assertEqual(len(db.sales_history()), count)

    def test_save_edit_approve(self):
        db.save_plan("2026-10-24", [rec("croissant", 44), rec("muffin", 22)])
        db.edit_item("2026-10-24", "croissant", 30, "School holiday")
        db.approve_plan("2026-10-24", "Derek")

        plan = db.get_plan("2026-10-24")
        croissant = plan[0]
        self.assertEqual(croissant["recommended"], 44)
        self.assertEqual(croissant["final"], 30)
        self.assertTrue(all(p["status"] == "approved" and p["decided_by"] == "Derek" for p in plan))

    def test_resending_replaces_the_plan(self):
        db.save_plan("2026-10-24", [rec("croissant", 44)])
        db.save_plan("2026-10-24", [rec("croissant", 41)])
        plan = db.latest_plan()
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["final"], 41)

    def test_settings_default_then_saved(self):
        self.assertEqual(db.get_setting("close_time"), db.DEFAULT_SETTINGS["close_time"])
        db.set_setting("close_time", "17:30")
        self.assertEqual(db.get_setting("close_time"), "17:30")

    def test_closing_count_saved_and_replaced(self):
        db.save_count("2026-10-23", "croissant", 43, 5)
        db.save_count("2026-10-23", "croissant", 43, 0, "2_4")   # counted again: replaces
        rows = [r for r in db.sales_history() if r["date"] == "2026-10-23"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["sold"], rows[0]["leftover"], rows[0]["sold_out_bucket"]), (43, 0, "2_4"))

    def test_edit_after_approval_needs_approving_again(self):
        db.save_plan("2026-10-24", [rec("croissant", 44)])
        db.approve_plan("2026-10-24", "Derek")
        db.reopen_plan("2026-10-24")
        plan = db.get_plan("2026-10-24")
        self.assertEqual((plan[0]["status"], plan[0]["decided_by"]), ("pending", None))

    def test_waste_summary_shape(self):
        items = [{"id": "croissant", "name": "Croissant", "cost": 2.0},
                 {"id": "sourdough", "name": "Sourdough loaf", "cost": 6.0},
                 {"id": "muffin", "name": "Banana muffin", "cost": 2.0}]
        w = db.waste_summary(items)
        self.assertEqual([x["item"] for x in w["this_week"]], ["Croissant", "Sourdough loaf", "Banana muffin"])
        # This week's leftovers = the last 7 days of sample data
        last7 = sorted({r["date"] for r in db.sales_history()})[-7:]
        expected = sum(r["leftover"] for r in db.sales_history() if r["date"] in last7 and r["item_id"] == "sourdough")
        self.assertEqual(w["this_week"][1]["leftovers"], expected)
        self.assertTrue(all(s["time"] in db.BUCKET_TIME.values() for s in w["sellouts"]))

    def test_daily_records_merge_plan_and_count(self):
        items = [{"id": "croissant", "name": "Croissant", "cost": 2.0}]
        db.save_plan("2026-10-23", [rec("croissant", 44)])
        db.save_count("2026-10-23", "croissant", 44, 3)
        day = db.daily_records(items, days=5)[0]
        self.assertEqual(day["date"], "2026-10-23")
        self.assertEqual(day["source"], "count")
        row = day["items"][0]
        self.assertEqual((row["planned"], row["baked"], row["sold"], row["leftover"]), (44, 44, 41, 3))
        self.assertEqual(day["waste_rm"], 6.0)

    def test_sample_days_are_labelled_sample(self):
        items = [{"id": "croissant", "name": "Croissant", "cost": 2.0}]
        day = db.daily_records(items, days=1)[0]
        self.assertEqual((day["source"], day["plan"]), ("sample", None))

    def test_log_newest_first(self):
        db.log("Derek", "manager", "Plan sent", "first")
        db.log("Aina", "staff", "Blocked", "second")
        self.assertEqual([e["details"] for e in db.recent_log()], ["second", "first"])


if __name__ == "__main__":
    unittest.main()
