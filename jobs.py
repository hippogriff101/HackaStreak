"""
The daily reminder + milestone job.

Lives in its own module (rather than inside scheduler.py) so the admin
panel's "run job now" button can call run_daily_job() directly in-process
instead of needing to talk to the scheduler container over the network.
Both processes share the same SQLite file on the same volume, so this is
safe for our scale, but note that running it from two places at once
(a manual trigger firing right as the daily cron does) isn't guarded
against — fine for a single small Hack Club Slack, worth revisiting if
this ever needs to be bulletproof.
"""

import logging
import os

import requests

import db
import hackatime

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
MILESTONE_CHANNEL_ID = os.getenv("MILESTONE_CHANNEL_ID")

SLACK_API_BASE = "https://slack.com/api"


def _slack_post(method, **payload):
    response = requests.post(
        f"{SLACK_API_BASE}/{method}",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        json=payload,
        timeout=10,
    )
    data = response.json()
    if not data.get("ok"):
        logger.warning("Slack API call %s failed: %s", method, data.get("error"))
    return data


def _send_dm(slack_user_id, text):
    # TODO: this opens a fresh IM channel per call. Fine at our current user
    # count; if that ever gets slow, cache slack_user_id -> im channel id.
    opened = _slack_post("conversations.open", users=slack_user_id)
    if not opened.get("ok"):
        return False
    channel_id = opened["channel"]["id"]
    posted = _slack_post("chat.postMessage", channel=channel_id, text=text)
    return posted.get("ok", False)


def _announce_milestone(hackatime_username, milestone):
    if not MILESTONE_CHANNEL_ID:
        logger.warning("MILESTONE_CHANNEL_ID not set, skipping milestone announcement")
        return
    _slack_post(
        "chat.postMessage",
        channel=MILESTONE_CHANNEL_ID,
        text=f":fire: *{hackatime_username}* just hit a *{milestone}-day* Hackatime streak!",
    )


def run_daily_job():
    """
    For every linked user: fetch their current streak, DM them if it's low
    and they haven't already been reminded today, and announce any newly
    crossed milestones in the configured channel.
    """
    run_id = db.start_job_run()
    low_streak_threshold = db.get_low_streak_threshold()
    milestones = db.get_milestones()
    today = db.today_iso()

    users_checked = 0
    users_skipped = 0
    errors = []

    for user in db.list_linked_users():
        slack_user_id = user["slack_user_id"]
        hackatime_username = user["hackatime_username"]

        result = hackatime.get_streak(hackatime_username)
        if not result["ok"]:
            users_skipped += 1
            errors.append(f"{hackatime_username}: {result['error']}")
            continue

        streak = result["streak"]
        db.record_streak_check(slack_user_id, streak)
        users_checked += 1

        if (
            user["reminder_opt_in"]
            and streak < low_streak_threshold
            and user["last_reminded_date"] != today
        ):
            sent = _send_dm(
                slack_user_id,
                f":wave: Your Hackatime streak is at {streak} day(s), below your "
                f"{low_streak_threshold}-day goal. Get some hacking in today!",
            )
            if sent:
                db.mark_reminded_today(slack_user_id)

        hits = db.parse_milestones_hit(user["milestones_hit"])
        for milestone in milestones:
            if streak >= milestone and milestone not in hits:
                _announce_milestone(hackatime_username, milestone)
                db.add_milestone_hit(slack_user_id, milestone, hits)
                hits.add(milestone)

    error_summary = "; ".join(errors) if errors else None
    db.finish_job_run(run_id, users_checked, users_skipped, error_summary)
    logger.info(
        "Daily job finished: %s checked, %s skipped", users_checked, users_skipped
    )
    return {
        "users_checked": users_checked,
        "users_skipped": users_skipped,
        "error_summary": error_summary,
    }
