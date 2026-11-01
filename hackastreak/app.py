import logging
import re

import requests
from slack_bolt import App
from slack_sdk.errors import SlackApiError

from . import config, db, hackatime, home

log = logging.getLogger(__name__)

app = App(token=config.SLACK_BOT_TOKEN)

SETUP_TEXT = (
    "You haven't linked your Hackatime account yet! Run `/hackastreak set <hackatime_username>` "
    "and then `/hackastreak` on its own will show your streak.\n"
    "Or look anyone up with `/hackastreak <hackatime_username>`."
)


def fetch_streak(username):
    """Returns (status, streak). status is 'ok', 'not_found', 'private' or 'error'."""
    try:
        code, data = hackatime.get_stats(username)
    except requests.exceptions.RequestException:
        log.exception("Network error while connecting to Hackatime API")
        return "error", None
    if code == 200:
        return "ok", int(data.get("streak", 0))
    if code == 404:
        return "not_found", None
    if code == 403:
        return "private", None
    log.warning("Hackatime API error: %s", code)
    return "error", None


def streak_message(username, own=False):
    status, streak = fetch_streak(username)
    if status == "ok":
        who = "Your" if own else f"{username}'s"
        return status, f"🔥 {who} current Hackatime streak is {streak} day/s."
    if status == "not_found":
        return status, f"User '{username}' does not exist."
    if status == "private":
        return status, f"User '{username}' has a private profile."
    return status, "Couldn't reach the Hackatime API. Try again later."


def clean_username(text):
    return text.strip().lstrip("@")


@app.command("/hackastreak")
def streak_command(ack, respond, command):
    ack()
    user_id = command["user_id"]
    channel_id = command.get("channel_id")
    args = command.get("text", "").split()

    if args and args[0].lower() == "set":
        if len(args) != 2:
            respond("Try this: `/hackastreak set <hackatime_username>`")
            db.log_event(user_id, "set", channel_id, outcome="bad_usage")
            return
        username = clean_username(args[1])
        status, _ = fetch_streak(username)
        if status == "not_found":
            respond(f"Couldn't find a Hackatime user called '{username}', double check the spelling!")
        elif status == "error":
            respond("Couldn't reach the Hackatime API to check that username. Try again later.")
        else:
            db.set_username(user_id, username)
            msg = f"Linked you to `{username}`! Now just run `/hackastreak` to see your streak."
            if status == "private":
                msg += "\nHeads up: that profile is private, so your streak won't show until it's public."
            respond(msg)
        log.info("%s set username %s (%s)", user_id, username, status)
        db.log_event(user_id, "set", channel_id, username, status)
        return

    if args:
        username = clean_username(args[0])
        status, msg = streak_message(username)
        respond(msg)
        log.info("%s looked up %s (%s)", user_id, username, status)
        db.log_event(user_id, "lookup", channel_id, username, status)
        return

    username = db.get_username(user_id)
    if not username:
        respond(SETUP_TEXT)
        db.log_event(user_id, "self", channel_id, outcome="not_linked")
        return
    status, msg = streak_message(username, own=True)
    respond(msg)
    log.info("%s looked up own streak %s (%s)", user_id, username, status)
    db.log_event(user_id, "self", channel_id, username, status)


def send_help(client, event, kind):
    channel = event["channel"]
    user = event["user"]
    try:
        client.reactions_add(channel=channel, timestamp=event["ts"], name="eyes_shaking")
    except SlackApiError as e:
        if e.response["error"] != "already_reacted":
            log.warning("Couldn't react: %s", e.response["error"])
    client.chat_postEphemeral(
        channel=channel,
        user=user,
        thread_ts=event.get("thread_ts"),
        text=home.HELP_TEXT,
    )
    log.info("Sent help to %s in %s (%s)", user, channel, kind)
    db.log_event(user, kind, channel)


@app.event("app_mention")
def on_mention(event, client):
    send_help(client, event, "mention")


@app.event("message")
def on_message(event, client, context):
    if event.get("channel") != config.PINGWORD_CHANNEL_ID:
        return
    if event.get("bot_id") or event.get("subtype") not in (None, "thread_broadcast", "file_share"):
        return
    text = event.get("text", "")
    # mentions are already handled by on_mention
    if f"<@{context.bot_user_id}>" in text:
        return
    # ignore formatting, spacing and case so *Hacka Streak* etc. still count
    if "hackastreak" in re.sub(r"[^a-z]", "", text.lower()):
        send_help(client, event, "pingword")


def publish_home(client, user_id):
    view = home.admin_view() if user_id in config.ADMIN_USER_IDS else home.help_view()
    client.views_publish(user_id=user_id, view=view)


@app.event("app_home_opened")
def on_home_opened(event, client):
    if event.get("tab") == "home":
        publish_home(client, event["user"])


@app.action("home_refresh")
def on_home_refresh(ack, body, client):
    ack()
    publish_home(client, body["user"]["id"])
