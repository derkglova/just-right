"""Daily timers the manager can change from the dashboard.

Two jobs run every day:
- plan_time:  send tomorrow's plan to the manager to approve (bot.send_plan)
- close_time: ask staff for the closing count (bot.start_count)

The times are saved in the database (db settings), so they survive a restart.
"""
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import bot
import db

TIMEZONE = "Asia/Kuala_Lumpur"

scheduler = BackgroundScheduler(timezone=TIMEZONE)


def send_plan_job():
    bot.send_plan()


def close_shop_job():
    bot.start_count()


JOBS = {"plan_time": send_plan_job, "close_time": close_shop_job}


def clean_time(text: str) -> str:
    """Check a time like "9:05" or "14:00" and return it as "HH:MM". Raises ValueError if invalid."""
    return datetime.strptime(text.strip(), "%H:%M").strftime("%H:%M")


def daily_at(hhmm: str) -> CronTrigger:
    hour, minute = hhmm.split(":")
    return CronTrigger(hour=int(hour), minute=int(minute), timezone=TIMEZONE)


def start() -> None:
    for key, job in JOBS.items():
        # misfire_grace_time: if the app was busy or restarting, still run up to 5 minutes late.
        scheduler.add_job(job, daily_at(db.get_setting(key)), id=key, misfire_grace_time=300)
    scheduler.start()


def set_time(key: str, hhmm: str) -> str:
    """Save a new daily time for one job and apply it right away."""
    hhmm = clean_time(hhmm)
    db.set_setting(key, hhmm)
    if scheduler.running:
        scheduler.reschedule_job(key, trigger=daily_at(hhmm))
    return hhmm


def next_run(key: str):
    """When the job runs next (ISO time), or None if the scheduler isn't running."""
    job = scheduler.get_job(key) if scheduler.running else None
    return job.next_run_time.isoformat() if job and job.next_run_time else None
