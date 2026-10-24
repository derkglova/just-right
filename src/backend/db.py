"""SQLite storage for plans, sales and the activity log.

Tables:
    plans(id, plan_date, item_id, item_name, usual, recommended, final, reason,
          status, decided_by, decided_at)
    daily_sales(date, item_id, baked, sold, leftover, sold_out_bucket, source)
    activity_log(id, ts, actor_name, role, action, details)
    settings(key, value)   -- e.g. close_time, baker_time ("HH:MM", set from the dashboard)
    event_days(date, note) -- one-off days (e.g. a big order); the AI forecast learns less from them

Each function opens its own connection, so the bot thread and the web server can
both use the database safely.

Run `python src/db.py` to print the latest plan and the activity log.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parent
DB_PATH = SRC_DIR / "just_right.db"
SALES_JSON = SRC_DIR / "data" / "sales_history.json"
TZ = ZoneInfo(os.environ.get("TZ", "Asia/Kuala_Lumpur"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    item_name   TEXT NOT NULL,
    usual       INTEGER NOT NULL,
    recommended INTEGER NOT NULL,
    final       INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL,          -- 'pending' or 'approved'
    decided_by  TEXT,
    decided_at  TEXT
);
CREATE TABLE IF NOT EXISTS daily_sales (
    date            TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    baked           INTEGER NOT NULL,
    sold            INTEGER NOT NULL,
    leftover        INTEGER NOT NULL,
    sold_out_bucket TEXT,
    source          TEXT NOT NULL DEFAULT 'sample',   -- 'sample' (generated) or 'count' (staff on Telegram)
    PRIMARY KEY (date, item_id)
);
CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    role       TEXT NOT NULL,
    action     TEXT NOT NULL,
    details    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_days (
    date TEXT PRIMARY KEY,
    note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Used until the manager changes them on the dashboard.
DEFAULT_SETTINGS = {
    "close_time": os.environ.get("CLOSE_TIME", "18:00"),  # ask staff for the closing count
    "baker_time": "20:00",                                # send the approved bake list to the baker
    "close_auto": "1",                                    # "1" = timer on, "0" = off
    "baker_auto": "1",
    "bake_list_sent_for": "",                             # plan date whose bake list was last sent
}


@contextmanager
def connect():
    """Open the database, commit if all went well, and always close it."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts: row["item_id"]
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def init() -> None:
    """Create the tables, and load the sample sales history (again if the sample file changed)."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        # Databases made before the 'source' column existed: add it.
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(daily_sales)")]
        if "source" not in columns:
            conn.execute("ALTER TABLE daily_sales ADD COLUMN source TEXT NOT NULL DEFAULT 'sample'")
            # Days that aren't in the sample file were counted by staff.
            sample_dates = sorted({r["date"] for r in json.loads(SALES_JSON.read_text())})
            conn.execute("UPDATE daily_sales SET source = 'count' WHERE date > ?", (sample_dates[-1],))
        rows = json.loads(SALES_JSON.read_text())
        loaded = conn.execute("SELECT COUNT(*) FROM daily_sales WHERE source = 'sample'").fetchone()[0]
        if loaded != len(rows):
            # Replace the old sample rows. Days counted by staff are kept (INSERT OR IGNORE).
            conn.execute("DELETE FROM daily_sales WHERE source = 'sample'")
            conn.executemany(
                "INSERT OR IGNORE INTO daily_sales (date, item_id, baked, sold, leftover, sold_out_bucket, source)"
                " VALUES (:date, :item, :baked, :sold, :leftover, :sold_out_bucket, 'sample')",
                rows,
            )


# ---- Sales ----

def sales_history() -> list[dict]:
    """All daily sales, in the same shape the planner expects (key 'item')."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM daily_sales ORDER BY date").fetchall()
    return [{**dict(r), "item": r["item_id"]} for r in rows]


def save_count(day: str, item_id: str, baked: int, leftover: int, sold_out_bucket: str = None) -> None:
    """Save one item's closing count. Counting again the same day replaces it."""
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO daily_sales (date, item_id, baked, sold, leftover, sold_out_bucket, source)"
            " VALUES (?, ?, ?, ?, ?, ?, 'count')",
            (day, item_id, baked, max(baked - leftover, 0), leftover, sold_out_bucket),
        )


def weekly_waste(costs: dict) -> list[dict]:
    """Leftovers per week (Monday to Sunday), in units and in RM.
    costs maps item_id -> ingredient cost of one unit."""
    weeks = {}
    for row in sales_history():
        day = date.fromisoformat(row["date"])
        monday = (day - timedelta(days=day.weekday())).isoformat()
        week = weeks.setdefault(monday, {"week_start": monday, "days": set(), "leftover_units": 0, "waste_rm": 0.0})
        week["days"].add(row["date"])
        week["leftover_units"] += row["leftover"]
        week["waste_rm"] += row["leftover"] * costs.get(row["item_id"], 0)
    for week in weeks.values():
        week["waste_rm"] = round(week["waste_rm"], 2)
        week["days"] = len(week["days"])   # first and last week may be partial
    return sorted(weeks.values(), key=lambda w: w["week_start"])


# Rough time of day for each sell-out bucket, for the dashboard's sell-out chart.
BUCKET_TIME = {"before_12": "11:00", "12_2": "13:00", "2_4": "15:00", "after_4": "17:00"}


def waste_summary(items: list[dict]) -> dict:
    """Waste and sell-outs for the dashboard. "This week" = the last 7 days with data,
    "last week" = the 7 days before that, then earlier weeks for the chart."""
    rows = sales_history()
    if not rows:
        return {"this_week": [], "sellouts": [], "last_week_sellouts": 0, "weekly": []}
    last_day = date.fromisoformat(rows[-1]["date"])
    names = {i["id"]: i["name"] for i in items}
    costs = {i["id"]: i["cost"] for i in items}

    def week_index(row):   # 0 = this week, 1 = last week, ...
        return (last_day - date.fromisoformat(row["date"])).days // 7

    this_week = []
    for item in items:
        mine = [r for r in rows if r["item_id"] == item["id"]]
        this_week.append({
            "item": item["name"],
            "cost": item["cost"],
            "leftovers": sum(r["leftover"] for r in mine if week_index(r) == 0),
            "last_week": sum(r["leftover"] for r in mine if week_index(r) == 1),
        })

    sellouts = [
        {"item": names.get(r["item_id"], r["item_id"]),
         "day": date.fromisoformat(r["date"]).strftime("%a"),
         "time": BUCKET_TIME.get(r["sold_out_bucket"], "17:00")}
        for r in rows if week_index(r) == 0 and r["leftover"] == 0 and r["sold_out_bucket"]
    ]
    last_week_sellouts = sum(1 for r in rows if week_index(r) == 1 and r["leftover"] == 0 and r["sold_out_bucket"])

    # Older full weeks (2+ weeks ago), oldest first, labelled by their first day.
    weekly = []
    for n in range(max(week_index(r) for r in rows), 1, -1):
        week = [r for r in rows if week_index(r) == n]
        if len({r["date"] for r in week}) < 7:
            continue   # skip a partial week at the start of the data
        start = last_day - timedelta(days=7 * n + 6)
        weekly.append({"week": f"{start.day} {start.strftime('%b')}",
                       "rm": round(sum(r["leftover"] * costs.get(r["item_id"], 0) for r in week), 2)})

    return {"this_week": this_week, "sellouts": sellouts,
            "last_week_sellouts": last_week_sellouts, "weekly": weekly[-6:]}


def daily_records(items: list[dict], days: int = 30) -> list[dict]:
    """Day by day, newest first: that day's plan and closing count side by side, with totals.
    items gives names and costs (from items.json)."""
    names = {i["id"]: i["name"] for i in items}
    costs = {i["id"]: i["cost"] for i in items}
    with connect() as conn:
        dates = [r[0] for r in conn.execute(
            "SELECT date FROM daily_sales UNION SELECT plan_date FROM plans ORDER BY 1 DESC LIMIT ?", (days,))]
        sales = [dict(r) for r in conn.execute(
            "SELECT * FROM daily_sales WHERE date >= ?", (dates[-1] if dates else "",))]

    events = event_days()
    today = datetime.now(TZ).date().isoformat()
    bake_list_sent_for = get_setting("bake_list_sent_for")
    records = []
    for day in dates:
        if day > today and day != bake_list_sent_for:
            continue   # a future plan only becomes a record once the baker has the list
        plan = {p["item_id"]: p for p in get_plan(day)}
        counted = {s["item_id"]: s for s in sales if s["date"] == day}
        rows = []
        for item_id in list(names) + [i for i in {**plan, **counted} if i not in names]:
            p, c = plan.get(item_id), counted.get(item_id)
            if not p and not c:
                continue
            rows.append({
                "item": names.get(item_id) or (p or {}).get("item_name", item_id),
                "planned": p["final"] if p else None,
                "recommended": p["recommended"] if p else None,
                "baked": c["baked"] if c else None,
                "sold": c["sold"] if c else None,
                "leftover": c["leftover"] if c else None,
                "sold_out": BUCKET_TIME.get(c["sold_out_bucket"]) if c and c["leftover"] == 0 else None,
                "waste_rm": round(c["leftover"] * costs.get(item_id, 0), 2) if c else None,
            })
        first_plan = next(iter(plan.values()), None)
        records.append({
            "date": day,
            "event": events.get(day),
            "counted": bool(counted),
            "source": "count" if any(c["source"] == "count" for c in counted.values()) else ("sample" if counted else None),
            "plan": {"status": first_plan["status"], "approved_by": first_plan["decided_by"],
                     "approved_at": first_plan["decided_at"]} if first_plan else None,
            "items": rows,
            "leftover": sum(r["leftover"] or 0 for r in rows),
            "waste_rm": round(sum(r["waste_rm"] or 0 for r in rows), 2),
            "sellouts": sum(1 for r in rows if r["sold_out"]),
        })
    return records


# ---- Plans ----

def save_plan(plan_date: str, recommendations) -> None:
    """Save a new pending plan for plan_date, replacing any earlier one for that day."""
    with connect() as conn:
        conn.execute("DELETE FROM plans WHERE plan_date = ?", (plan_date,))
        conn.execute("DELETE FROM settings WHERE key = 'bake_list_sent_for' AND value = ?", (plan_date,))
        conn.executemany(
            "INSERT INTO plans (plan_date, item_id, item_name, usual, recommended, final, reason, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
            [(plan_date, r.item_id, r.name, r.usual, r.quantity, r.quantity, r.reason) for r in recommendations],
        )


def get_plan(plan_date: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM plans WHERE plan_date = ? ORDER BY id", (plan_date,)).fetchall()
    return [dict(r) for r in rows]


def latest_plan() -> list[dict]:
    """The most recent plan (all its items), or [] if there is none yet."""
    with connect() as conn:
        row = conn.execute("SELECT MAX(plan_date) FROM plans").fetchone()
    return get_plan(row[0]) if row[0] else []


def previous_bake(plan_date: str) -> dict:
    """{item_id: amount} baked the day before plan_date: that day's plan, or its closing count."""
    day_before = (date.fromisoformat(plan_date) - timedelta(days=1)).isoformat()
    amounts = {p["item_id"]: p["final"] for p in get_plan(day_before)}
    if not amounts:
        with connect() as conn:
            amounts = {r["item_id"]: r["baked"] for r in conn.execute(
                "SELECT item_id, baked FROM daily_sales WHERE date = ?", (day_before,))}
    return amounts


def edit_item(plan_date: str, item_id: str, final: int, reason: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE plans SET final = ?, reason = ? WHERE plan_date = ? AND item_id = ?",
            (final, reason, plan_date, item_id),
        )


def reopen_plan(plan_date: str) -> None:
    """Back to pending, e.g. after an approved plan is edited, so it must be approved again."""
    with connect() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'bake_list_sent_for' AND value = ?", (plan_date,))
        conn.execute(
            "UPDATE plans SET status = 'pending', decided_by = NULL, decided_at = NULL WHERE plan_date = ?",
            (plan_date,),
        )


def approve_plan(plan_date: str, decided_by: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE plans SET status = 'approved', decided_by = ?, decided_at = ? WHERE plan_date = ?",
            (decided_by, now(), plan_date),
        )


# ---- Event days ----

def mark_event(day: str, note: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO event_days VALUES (?, ?)", (day, note))


def event_days() -> dict:
    """{date: note} for every one-off event day."""
    with connect() as conn:
        return {r["date"]: r["note"] for r in conn.execute("SELECT * FROM event_days")}


# ---- Settings ----

def get_setting(key: str) -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS[key]


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))


# ---- Activity log ----

def log(actor_name: str, role: str, action: str, details: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO activity_log (ts, actor_name, role, action, details) VALUES (?, ?, ?, ?, ?)",
            (now(), actor_name, role, action, details),
        )


def recent_log(limit: int = 20) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init()
    plan = latest_plan()
    if plan:
        print(f"Latest plan: {plan[0]['plan_date']} ({plan[0]['status']})")
        for p in plan:
            print(f"  {p['item_name']:<16} recommended {p['recommended']:>3}  final {p['final']:>3}  {p['reason']}")
    else:
        print("No plan yet. Send /plan in Telegram.")
    print("\nActivity log (newest first):")
    for e in recent_log():
        print(f"  {e['ts']}  {e['actor_name']} ({e['role']})  {e['action']}: {e['details']}")
