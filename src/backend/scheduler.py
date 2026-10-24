"""Daily timers the manager can change from the dashboard.

Two jobs run every day:
- close: at close_time, ask staff for the closing count (bot.start_count).
         When the count is done, the manager gets tomorrow's plan straight away (bot.finish_count).
- baker: at baker_time, send the approved bake list to the baker if approving didn't already (backup)

close and baker can be switched off from the dashboard (close_auto, baker_auto).
Times and switches are saved in the database (db settings), so they survive a restart.
"""
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import bot
import db

TIMEZONE = "Asia/Kuala_Lumpur"

scheduler = BackgroundScheduler(timezone=TIMEZONE)


def close_shop_job():
    bot.start_count()


def baker_job():
    problem = bot.send_bake_list(skip_if_sent=True)
    if problem == "Approve the plan first.":
        bot.bot.send_message(bot.MANAGER_ID, "Tomorrow's plan isn't approved yet, so the bake list wasn't sent.")


# job name -> (function, time setting, on/off setting or None if always on)
JOBS = {
    "close": (close_shop_job, "close_time", "close_auto"),
    "baker": (baker_job, "baker_time", "baker_auto"),
}


def clean_time(text: str) -> str:
    """Check a time like "9:05" or "14:00" and return it as "HH:MM". Raises ValueError if invalid."""
    return datetime.strptime(text.strip(), "%H:%M").strftime("%H:%M")


def daily_at(hhmm: str) -> CronTrigger:
    hour, minute = hhmm.split(":")
    return CronTrigger(hour=int(hour), minute=int(minute), timezone=TIMEZONE)


def is_on(name: str) -> bool:
    auto_key = JOBS[name][2]
    return auto_key is None or db.get_setting(auto_key) == "1"


def start() -> None:
    for name, (job, time_key, _) in JOBS.items():
        # misfire_grace_time: if the app was busy or restarting, still run up to 5 minutes late.
        scheduler.add_job(job, daily_at(db.get_setting(time_key)), id=name, misfire_grace_time=300)
        if not is_on(name):
            scheduler.pause_job(name)
    scheduler.start()


def update(name: str, time: str = None, auto: bool = None) -> None:
    """Change a job's daily time and/or switch it on or off, and apply it right away."""
    _, time_key, auto_key = JOBS[name]
    if time is not None:
        db.set_setting(time_key, clean_time(time))
    if auto is not None and auto_key:
        db.set_setting(auto_key, "1" if auto else "0")
    if scheduler.running:
        scheduler.reschedule_job(name, trigger=daily_at(db.get_setting(time_key)))
        if is_on(name):
            scheduler.resume_job(name)
        else:
            scheduler.pause_job(name)


def status(name: str) -> dict:
    """Time, on/off and next run (ISO time, or None if off or not running) for one job."""
    job = scheduler.get_job(name) if scheduler.running else None
    return {
        "time": db.get_setting(JOBS[name][1]),
        "auto": is_on(name),
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }
