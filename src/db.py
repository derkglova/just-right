"""SQLite storage for plans, sales and the activity log.

Tables:
    plans(id, plan_date, item_id, item_name, usual, recommended, final, reason,
          status, decided_by, decided_at)
    daily_sales(date, item_id, baked, sold, leftover, sold_out_bucket)
    activity_log(id, ts, actor_name, role, action, details)

Each function opens its own connection, so the bot thread and the web server can
both use the database safely.

Run `python src/db.py` to print the latest plan and the activity log.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
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
"""


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
    """Create the tables, and load the sample sales history the first time."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM daily_sales").fetchone()[0] == 0:
            rows = json.loads(SALES_JSON.read_text())
            conn.executemany(
                "INSERT INTO daily_sales VALUES (:date, :item, :baked, :sold, :leftover, :sold_out_bucket)",
                rows,
            )


# ---- Sales ----

def sales_history() -> list[dict]:
    """All daily sales, in the same shape the planner expects (key 'item')."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM daily_sales ORDER BY date").fetchall()
    return [{**dict(r), "item": r["item_id"]} for r in rows]


# ---- Plans ----

def save_plan(plan_date: str, recommendations) -> None:
    """Save a new pending plan for plan_date, replacing any earlier one for that day."""
    with connect() as conn:
        conn.execute("DELETE FROM plans WHERE plan_date = ?", (plan_date,))
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


def edit_item(plan_date: str, item_id: str, final: int, reason: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE plans SET final = ?, reason = ? WHERE plan_date = ? AND item_id = ?",
            (final, reason, plan_date, item_id),
        )


def approve_plan(plan_date: str, decided_by: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE plans SET status = 'approved', decided_by = ?, decided_at = ? WHERE plan_date = ?",
            (decided_by, now(), plan_date),
        )


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
