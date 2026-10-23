"""SQLite storage.

TODO (build with Claude Code):
- init(): create tables if missing and load data/sales_history.json into daily_sales once.
    plans(id, plan_date, item_id, recommended, final, reason, status, decided_by, decided_at)
    daily_sales(date, item_id, baked, sold, leftover, sold_out_bucket)
    activity_log(id, ts, actor_name, role, action, details)
- log(actor_name, role, action, details): append to activity_log.
- Helpers for the dashboard: latest_plan(), recent_log(limit=20), weekly_waste_rm().
"""
