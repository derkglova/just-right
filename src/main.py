"""Entry point: runs the web dashboard and the Telegram bot together.

TODO (build with Claude Code):
- Load env vars (python-dotenv locally; Replit Secrets in deployment).
- Init the database (db.init()).
- Start the Telegram bot polling in a background thread (bot.run()).
- Schedule the daily plan at PLAN_TIME (Asia/Kuala_Lumpur) with APScheduler -> bot.send_plan().
- Flask routes:
    GET  /                 -> dashboard.html (plan status, activity log, waste chart, items)
    POST /send-plan        -> bot.send_plan() now (demo button)
    GET  /api/plan         -> tomorrow's plan as JSON
- Listen on 0.0.0.0:$PORT (Replit needs this).
"""
import os

from flask import Flask, render_template

from planner import load_data, make_plan

app = Flask(__name__)


@app.get("/")
def dashboard():
    items, history = load_data()
    plan = make_plan(items, history)
    return render_template("dashboard.html", plan=plan, items=items)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
