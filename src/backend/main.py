"""Entry point: runs the dashboard, its JSON API, the Telegram bot and the daily timers in one process.

- Loads env vars (.env locally; Replit Secrets in deployment).
- Sets up the database.
- Starts the Telegram bot polling in a background thread, and the daily timers (scheduler.py).
- Serves the dashboard (src/frontend) and the API on 0.0.0.0:$PORT (Replit needs this).

All API endpoints, with examples: docs/documentation.md
"""
import csv
import io
import json
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

load_dotenv()

import bot  # noqa: E402  (needs the env vars above)
import db  # noqa: E402
import forecast  # noqa: E402
import scheduler  # noqa: E402
import weather  # noqa: E402
from planner import DATA_DIR, load_data, target_level  # noqa: E402

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
        db.save_plan(tomorrow(), bot.work_out_plan(tomorrow()))
        plan = db.get_plan(tomorrow())
    return plan


def plan_json(rows: list[dict]) -> dict:
    first = rows[0]
    return {
        "date": first["plan_date"],
        "status": first["status"],
        "approved_by": first["decided_by"],
        "approved_at": first["decided_at"],
        "bake_list_sent": db.get_setting("bake_list_sent_for") == first["plan_date"],
        "items": [
            {
                "item_id": r["item_id"],
                "item": r["item_name"],
                "usual": r["usual"],
                "recommended": r["recommended"],
                "bake": r["final"],
                "edited": r["final"] != r["recommended"],
                "reason": r["reason"],
            }
            for r in rows
        ],
    }


@app.get("/api/plan")
def api_plan():
    return jsonify(plan_json(current_plan()))


@app.get("/api/plan/today")
def api_plan_today():
    today = datetime.now(bot.TZ).date().isoformat()
    plan = db.get_plan(today)
    if not plan:
        return jsonify({"date": today, "status": "none", "approved_by": None, "approved_at": None, "items": []})
    return jsonify(plan_json(plan))


@app.post("/api/recalculate")
def api_recalculate():
    db.save_plan(tomorrow(), bot.work_out_plan(tomorrow()))
    db.log("Dashboard", "manager", "Plan recalculated", f"New amounts for {tomorrow()} from the latest sales")
    return jsonify(plan_json(db.get_plan(tomorrow())))


@app.post("/api/send-plan")
def api_send_plan():
    bot.send_plan(bot.MANAGER_ID, "Dashboard", "manager")
    return jsonify(plan_json(db.latest_plan()))


# ---- Activity log ----

LOG_TYPES = {"Plan approved": "approval", "Plan edited": "edit", "Event day": "edit",
             "Closing count": "count", "Count requested": "count"}


@app.get("/api/log")
def api_log():
    limit = request.args.get("limit", default=30, type=int)
    return jsonify([
        {
            "who": e["actor_name"],
            "role": e["role"],
            "type": LOG_TYPES.get(e["action"], "plan"),
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


@app.get("/api/forecast")
def api_forecast():
    items, _ = load_data()
    history = db.sales_history()
    events = db.event_days()
    dates = sorted(r["date"] for r in history)
    weather_by_date = weather.history(date.fromisoformat(dates[0]), date.fromisoformat(dates[-1]))
    days = forecast.backtest(items, history, weather_by_date, events)
    recent = days[-30:]
    return jsonify({
        "days": days[-60:],
        "ai_miss": round(sum(d["ai"] for d in recent) / len(recent), 1) if recent else None,
        "old_miss": round(sum(d["old"] for d in recent) / len(recent), 1) if recent else None,
        "trained_days": len(set(dates)),
        "event_days": len(events),
        "effects": forecast.learned_effects(items, history, weather_by_date, events),
        "tomorrow": {"date": tomorrow(), **weather.for_day(date.fromisoformat(tomorrow()))},
    })


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
