"""Entry point: runs the web dashboard and the Telegram bot together in one process.

- Loads env vars (.env locally; Replit Secrets in deployment).
- Sets up the database.
- Starts the Telegram bot polling in a background thread.
- Serves the dashboard and a small JSON API on 0.0.0.0:$PORT (Replit needs this).

API (all JSON, sample data):
    GET  /api/plan        latest plan: status, who approved, each item's numbers and reason
    GET  /api/log         activity log, newest first (?limit=20)
    GET  /api/waste       leftovers per week in units and RM
    GET  /api/items       items with price, cost, usual batch and target level
    POST /api/send-plan   send tomorrow's plan to the manager on Telegram now (demo button)

TODO (next step): 2 PM scheduler (APScheduler -> bot.send_plan()).
"""
import os
import threading

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

import bot  # noqa: E402  (needs the env vars above)
import db  # noqa: E402
from planner import load_data, make_plan, target_level  # noqa: E402

app = Flask(__name__)


@app.after_request
def allow_any_origin(response):
    # Lets a page hosted somewhere else (or opened from a local file) call the API.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.get("/")
def dashboard():
    items, history = load_data()
    plan = make_plan(items, history)
    return render_template("dashboard.html", plan=plan, items=items)


def plan_json(rows: list[dict]) -> dict:
    """Turn the plan rows from the database into one object for the dashboard."""
    if not rows:
        return {"plan_date": None, "status": "none", "decided_by": None, "decided_at": None, "items": []}
    first = rows[0]
    return {
        "plan_date": first["plan_date"],
        "status": first["status"],            # 'pending' or 'approved'
        "decided_by": first["decided_by"],
        "decided_at": first["decided_at"],
        "items": [
            {
                "item_id": r["item_id"],
                "name": r["item_name"],
                "usual": r["usual"],
                "recommended": r["recommended"],   # what the planner suggested
                "final": r["final"],               # after any manager edit
                "edited": r["final"] != r["recommended"],
                "reason": r["reason"],
            }
            for r in rows
        ],
    }


@app.get("/api/plan")
def api_plan():
    return jsonify(plan_json(db.latest_plan()))


@app.get("/api/log")
def api_log():
    limit = request.args.get("limit", default=20, type=int)
    return jsonify(db.recent_log(limit))


@app.get("/api/waste")
def api_waste():
    items, _ = load_data()
    return jsonify(db.weekly_waste({i["id"]: i["cost"] for i in items}))


@app.get("/api/items")
def api_items():
    items, _ = load_data()
    return jsonify([{**i, "target_level": round(target_level(i["price"], i["cost"]), 2)} for i in items])


@app.post("/api/send-plan")
def api_send_plan():
    bot.send_plan(bot.MANAGER_ID, "Dashboard", "manager")
    return jsonify(plan_json(db.latest_plan()))


if __name__ == "__main__":
    db.init()
    # daemon=True: the bot thread stops when the main program stops.
    threading.Thread(target=bot.run, daemon=True).start()
    print("Bot running. Dashboard on http://localhost:" + os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
