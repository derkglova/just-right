"""Entry point: runs the web dashboard and the Telegram bot together in one process.

- Loads env vars (.env locally; Replit Secrets in deployment).
- Sets up the database.
- Starts the Telegram bot polling in a background thread.
- Serves the dashboard on 0.0.0.0:$PORT (Replit needs this).

TODO (next steps): 2 PM scheduler (APScheduler -> bot.send_plan()),
POST /send-plan (demo button) and GET /api/plan.
"""
import os
import threading

from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()

import bot  # noqa: E402  (needs the env vars above)
import db  # noqa: E402
from planner import load_data, make_plan  # noqa: E402

app = Flask(__name__)


@app.get("/")
def dashboard():
    items, history = load_data()
    plan = make_plan(items, history)
    return render_template("dashboard.html", plan=plan, items=items)


if __name__ == "__main__":
    db.init()
    # daemon=True: the bot thread stops when the main program stops.
    threading.Thread(target=bot.run, daemon=True).start()
    print("Bot running. Dashboard on http://localhost:" + os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
