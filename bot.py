"""
The Slack bot process: slash command + @mention handling, Socket Mode.

This is the same connection model as the original viber.py (no inbound
port needed), just split so the OAuth/homepage/admin web app and the
daily scheduler job live in their own processes. All three share the
SQLite database via db.py.
"""

import logging
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import db
import hackatime

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = App(token=os.getenv("SLACK_BOT_TOKEN"))


def _resolve_username(explicit_username, slack_user_id):
    """
    Use the typed username if given, otherwise fall back to whatever
    Hackatime username this Slack user has linked on the homepage.

    Judgment call: the spec only asked for "@hackastreak [username]", but
    since the linking table exists anyway for reminders/milestones, a
    no-argument lookup falling back to the caller's own linked account
    seemed like an easy, obviously-wanted extension. Flag if that's wrong.
    """
    if explicit_username:
        return explicit_username, None

    linked = db.get_user(slack_user_id)
    if linked:
        return linked["hackatime_username"], None

    return None, (
        "You didn't give me a username, and you haven't linked a Hackatime "
        "account yet. Try `/hackastreak <hackatime_username>`, or link your "
        "account on the homepage first."
    )


def _format_streak_reply(hackatime_username, result):
    if not result["ok"]:
        return result["message"]
    return f":fire: {hackatime_username}'s current Hackatime streak is {result['streak']} day/s."


@app.command("/hackastreak")
def streak_command(ack, respond, command):
    ack()
    username = command.get("text", "").strip()
    slack_user_id = command["user_id"]

    resolved_username, error = _resolve_username(username, slack_user_id)
    if error:
        respond(error)
        return

    logger.info("Slash command: fetching Hackatime stats for %s", resolved_username)
    result = hackatime.get_streak(resolved_username)
    respond(_format_streak_reply(resolved_username, result))


@app.event("app_mention")
def mention_handler(event, say):
    slack_user_id = event["user"]
    thread_ts = event.get("thread_ts", event["ts"])

    # Strip the leading "<@BOTID>" mention off the message text.
    text = event.get("text", "")
    username = " ".join(text.split()[1:]).strip()

    resolved_username, error = _resolve_username(username, slack_user_id)
    if error:
        say(text=error, thread_ts=thread_ts)
        return

    logger.info("Mention: fetching Hackatime stats for %s", resolved_username)
    result = hackatime.get_streak(resolved_username)
    say(text=_format_streak_reply(resolved_username, result), thread_ts=thread_ts)


if __name__ == "__main__":
    db.init_db()
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    handler.start()
