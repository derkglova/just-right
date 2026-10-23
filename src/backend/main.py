"""Entry point: runs the dashboard, its JSON API, the Telegram bot and the daily timers in one process.

- Loads env vars (.env locally; Replit Secrets in deployment).
- Sets up the database.
- Starts the Telegram bot polling in a background thread, and the daily timers (scheduler.py).
- Serves the dashboard (src/frontend) and the API on 0.0.0.0:$PORT (Replit needs this).

API (all JSON, sample data). Shapes match what src/frontend expects:
    GET  /api/plan            tomorrow's plan: status, who approved, each item's numbers and reason
    POST /api/plan/item       change one item's quantity {"item": "Croissant", "qty": 30}
    POST /api/approve         approve the plan (also sends the bake list to the baker)
    POST /api/send-plan       send the plan to the manager on Telegram now
    GET  /api/log             activity log, newest first (?limit=30)
    GET  /api/waste           waste and sell-outs this week, last week and earlier weeks
    GET  /api/records         day by day: plan vs closing count, waste RM (?days=30)
    GET  /api/records.csv     the same, as a CSV download (one row per day per item)
    GET  /api/items           items with price, cost and usual batch
    POST /api/items           save edited prices, costs and usual batches
    POST /api/telegram/close  ask staff for the closing count now
    POST /api/telegram/baker  send the approved bake list to the baker now
    GET  /api/schedule        daily timers: {"close": {"time", "auto", "next_run"}, "baker": {...}, "plan": {...}}
    POST /api/schedule        change timers, e.g. {"close": {"time": "18:30", "auto": true}}
"""
import csv
import io
import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

load_dotenv()

import bot  # noqa: E402  (needs the env vars above)
import db  # noqa: E402
import scheduler  # noqa: E402
from planner import DATA_DIR, load_data, make_plan, target_level  # noqa: E402

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
DASHBOARD_FILE = "Just Right Manager.dc.html"

# static_url_path="" serves support.js and image-slot.js from the frontend folder at /support.js etc.
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")


@app.after_request
def allow_any_origin(response):
    # Lets a page hosted somewhere else (or opened from a local file) call the API.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.get("/")
def dashboard():
    # Sent as a plain file: the design uses {{ }} itself, so Flask must not treat it as a template.
    return send_from_directory(FRONTEND_DIR, DASHBOARD_FILE)


# ---- Plan ----

def tomorrow() -> str:
    return (datetime.now(bot.TZ) + timedelta(days=1)).date().isoformat()


def current_plan() -> list[dict]:
    """Tomorrow's plan. If there is none yet, make it (pending, no Telegram message)."""
    plan = db.get_plan(tomorrow())
    if not plan:
        items, _ = load_data()
        db.save_plan(tomorrow(), make_plan(items, db.sales_history()))
        plan = db.get_plan(tomorrow())
    return plan


def plan_json(rows: list[dict]) -> dict:
    first = rows[0]
    return {
        "date": first["plan_date"],
        "status": first["status"],            # 'pending' or 'approved'
        "approved_by": first["decided_by"],
        "approved_at": first["decided_at"],
        "items": [
            {
                "item_id": r["item_id"],
                "item": r["item_name"],
                "usual": r["usual"],
                "recommended": r["recommended"],   # what the planner suggested
                "bake": r["final"],                # after any manager edit
                "edited": r["final"] != r["recommended"],
                "reason": r["reason"],
            }
            for r in rows
        ],
    }


@app.get("/api/plan")
def api_plan():
    return jsonify(plan_json(current_plan()))


@app.post("/api/plan/item")
def api_edit_item():
    data = request.get_json(silent=True) or {}
    plan = current_plan()
    row = next((p for p in plan if data.get("item") in (p["item_name"], p["item_id"])), None)
    qty = data.get("qty")
    if row is None or not isinstance(qty, int) or qty < 0:
        return jsonify({"error": "Send an item name and a whole number qty"}), 400

    plan_date = row["plan_date"]
    if plan[0]["status"] == "approved":
        db.reopen_plan(plan_date)   # changed after approval: needs approving again
    db.edit_item(plan_date, row["item_id"], qty, "Edited by manager on the dashboard")
    db.log("Dashboard", "manager", "Plan edited", f"{row['item_name']} {row['final']} -> {qty}")
    return jsonify(plan_json(db.get_plan(plan_date)))


@app.post("/api/approve")
def api_approve():
    plan = current_plan()
    if plan[0]["status"] != "approved":
        bot.approve_plan(plan[0]["plan_date"], "Dashboard")
    return jsonify(plan_json(db.get_plan(plan[0]["plan_date"])))


@app.post("/api/send-plan")
def api_send_plan():
    bot.send_plan(bot.MANAGER_ID, "Dashboard", "manager")
    return jsonify(plan_json(db.latest_plan()))


# ---- Activity log ----

LOG_TYPES = {"Plan approved": "approval", "Plan edited": "edit",
             "Closing count": "count", "Count requested": "count"}


@app.get("/api/log")
def api_log():
    limit = request.args.get("limit", default=30, type=int)
    return jsonify([
        {
            "who": e["actor_name"],
            "role": e["role"],
            "type": LOG_TYPES.get(e["action"], "plan"),   # the design's filters: count / approval / edit
            "action": f"{e['action']}: {e['details']}",
            "at": e["ts"],
        }
        for e in db.recent_log(limit)
    ])


# ---- Waste and items ----

@app.get("/api/waste")
def api_waste():
    items, _ = load_data()
    return jsonify(db.waste_summary(items))


@app.get("/api/records")
def api_records():
    items, _ = load_data()
    return jsonify(db.daily_records(items, request.args.get("days", default=30, type=int)))


@app.get("/api/records.csv")
def api_records_csv():
    items, _ = load_data()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "item", "planned", "approved_by", "baked", "sold", "leftover",
                     "sold_out_around", "waste_rm", "source"])
    for day in db.daily_records(items, request.args.get("days", default=365, type=int)):
        approved_by = (day["plan"] or {}).get("approved_by") or ""
        source = {"count": "staff count", "sample": "sample data"}.get(day["source"], "")
        for r in day["items"]:
            writer.writerow([day["date"], r["item"], r["planned"], approved_by, r["baked"], r["sold"],
                             r["leftover"], r["sold_out"], r["waste_rm"], source])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=just-right-records.csv"})


@app.get("/api/items")
def api_items():
    items, _ = load_data()
    return jsonify([{**i, "target_level": round(target_level(i["price"], i["cost"]), 2)} for i in items])


@app.post("/api/items")
def api_save_items():
    """Save edited prices, costs and usual batches. Matched by id or name; other fields are kept."""
    edits = request.get_json(silent=True) or []
    items, _ = load_data()
    for item in items:
        edit = next((e for e in edits if e.get("id") == item["id"] or e.get("name") == item["name"]), None)
        if not edit:
            continue
        try:
            price, cost, batch = float(edit["price"]), float(edit["cost"]), int(edit["usual_batch"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": f"Bad numbers for {item['name']}"}), 400
        if not 0 < cost < price or batch < 1:
            return jsonify({"error": f"{item['name']}: cost must be above 0 and below the price"}), 400
        item.update(price=price, cost=cost, usual_batch=batch)
    (DATA_DIR / "items.json").write_text(json.dumps(items, indent=2) + "\n")
    db.log("Dashboard", "manager", "Items updated", "Prices, costs or usual batches changed")
    return api_items()


# ---- Telegram buttons and timers ----

@app.post("/api/telegram/close")
def api_close_shop():
    sent = bot.start_count("Dashboard", "manager")
    return jsonify({"sent_to": sent})


@app.post("/api/telegram/baker")
def api_send_bake_list():
    problem = bot.send_bake_list()
    if problem:
        return jsonify({"error": problem}), 409
    return jsonify({"sent": True})


def schedule_json() -> dict:
    return {name: scheduler.status(name) for name in scheduler.JOBS}


@app.get("/api/schedule")
def api_schedule():
    return jsonify(schedule_json())


@app.post("/api/schedule")
def api_set_schedule():
    data = request.get_json(silent=True) or {}
    changes = []
    for name in scheduler.JOBS:
        if not isinstance(data.get(name), dict):
            continue
        new = data[name]
        try:
            scheduler.update(name, new.get("time"), new.get("auto"))
        except (ValueError, AttributeError):
            return jsonify({"error": f"{name} time must look like 14:00"}), 400
        s = scheduler.status(name)
        changes.append(f"{name} {s['time']} ({'on' if s['auto'] else 'off'})")
    if changes:
        db.log("Dashboard", "manager", "Schedule changed", ", ".join(changes))
    return jsonify(schedule_json())


if __name__ == "__main__":
    db.init()
    # daemon=True: the bot thread stops when the main program stops.
    threading.Thread(target=bot.run, daemon=True).start()
    scheduler.start()
    print("Bot running. Dashboard on http://localhost:" + os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
