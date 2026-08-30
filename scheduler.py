"""
The scheduler process: runs the daily reminder/milestone job once a day.

Kept as its own container (per CLAUDE.md's hosting notes) rather than
folded into bot.py or webapp.py, so a stuck or slow job run can't take
either of those down. Uses APScheduler's BlockingScheduler since this
process has nothing else to do but wait for its one daily trigger.

Note: this runs on a single fixed hour for every user (no per-user
timezone support yet -- see the "timezone-aware scheduling" suggestion
in CLAUDE.md). DAILY_JOB_HOUR is in UTC.
"""

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

import db
from jobs import run_daily_job

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DAILY_JOB_HOUR = int(os.getenv("DAILY_JOB_HOUR", "13"))  # 13:00 UTC by default


def scheduled_run():
    logger.info("Starting scheduled daily job run")
    result = run_daily_job()
    logger.info("Scheduled daily job run complete: %s", result)


if __name__ == "__main__":
    db.init_db()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(scheduled_run, "cron", hour=DAILY_JOB_HOUR, minute=0)
    logger.info("Scheduler started, daily job set for %02d:00 UTC", DAILY_JOB_HOUR)
    scheduler.start()
