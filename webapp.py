"""
The web app process: Slack "Add to Slack" OAuth, the homepage linking form,
and the /admin panel gated by Hack Club Auth.

This is the one process that needs a public HTTPS URL (see CLAUDE.md's
hosting notes -- everything else in this project talks outbound only).
Slack OAuth here identifies *which Slack user* is filling out the linking
form; it deliberately does not by itself grant them a Hackatime username --
that's a separate step (the /link form below), per CLAUDE.md.
"""

import logging
import os
import secrets

import requests
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

import db
import hackatime
from jobs import run_daily_job

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET")

SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")

HACKATIME_CLIENT_ID = os.getenv("HACKATIME_CLIENT_ID")
HACKATIME_CLIENT_SECRET = os.getenv("HACKATIME_CLIENT_SECRET")
HACKATIME_REDIRECT_URI = os.getenv("HACKATIME_REDIRECT_URI")

# Only scopes this bot actually uses: slash command + mentions (already
# granted via Socket Mode on the bot process, but Slack still wants them
# declared on the same app) and posting messages/DMs for the daily job.
SLACK_BOT_SCOPES = "commands,app_mentions:read,chat:write,im:write"

ADMIN_ALLOWLIST = {
    entry.strip()
    for entry in os.getenv("ADMIN_ALLOWLIST", "").split(",")
    if entry.strip()
}

oauth = OAuth(app)
oauth.register(
    name="hackclub_auth",
    client_id=os.getenv("AUTH_CLIENT_ID"),
    client_secret=os.getenv("AUTH_CLIENT_SECRET"),
    server_metadata_url="https://auth.hackclub.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid profile email slack_id verification_status"},
)


# ---------------------------------------------------------------------------
# Homepage + Hackatime linking
# ---------------------------------------------------------------------------

@app.route("/")
def homepage():
    slack_user_id = session.get("slack_user_id")
    linked_user = db.get_user(slack_user_id) if slack_user_id else None
    return render_template(
        "index.html",
        slack_user_id=slack_user_id,
        linked_user=linked_user,
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@app.route("/link", methods=["POST"])
def link():
    slack_user_id = session.get("slack_user_id")
    if not slack_user_id:
        return redirect(url_for("homepage", error="Add HackaStreak to Slack first."))

    hackatime_username = request.form.get("hackatime_username", "").strip()
    if not hackatime_username:
        return redirect(url_for("homepage", error="Enter a Hackatime username."))

    result = hackatime.get_streak(hackatime_username)
    if not result["ok"]:
        return redirect(url_for("homepage", error=result["message"]))

    db.link_user(slack_user_id, session.get("team_id", ""), hackatime_username)
    return redirect(url_for("homepage", message=f"Linked to Hackatime user '{hackatime_username}'."))


@app.route("/unlink", methods=["POST"])
def unlink():
    slack_user_id = session.get("slack_user_id")
    if slack_user_id:
        db.unlink_user(slack_user_id)
    return redirect(url_for("homepage", message="Unlinked your Hackatime account."))


# ---------------------------------------------------------------------------
# Hackatime OAuth ("Verify with Hackatime") -- an alternative to typing a
# username: proves the visitor owns this Hackatime account by checking that
# its slack_id (from the OAuth "profile" scope) matches the Slack account
# already linked via the Slack OAuth step above. Kept alongside the manual
# /link form above rather than replacing it, since get_streak_by_id()'s
# assumption (numeric OAuth id == valid {user} for the stats endpoint)
# hasn't been checked against a live account yet -- see hackatime.py.
# ---------------------------------------------------------------------------

@app.route("/hackatime/oauth/start")
def hackatime_oauth_start():
    if not session.get("slack_user_id"):
        return redirect(url_for("homepage", error="Add HackaStreak to Slack first."))

    state = secrets.token_urlsafe(16)
    session["hackatime_oauth_state"] = state
    authorize_url = (
        "https://hackatime.hackclub.com/oauth/authorize"
        f"?client_id={HACKATIME_CLIENT_ID}"
        f"&redirect_uri={HACKATIME_REDIRECT_URI}"
        "&response_type=code"
        "&scope=profile"
        f"&state={state}"
    )
    return redirect(authorize_url)


@app.route("/hackatime/oauth/callback")
def hackatime_oauth_callback():
    if request.args.get("state") != session.pop("hackatime_oauth_state", None):
        return redirect(url_for("homepage", error="Hackatime verification failed (state mismatch). Try again."))

    code = request.args.get("code")
    slack_user_id = session.get("slack_user_id")
    if not code or not slack_user_id:
        return redirect(url_for("homepage", error="Hackatime verification was cancelled or failed."))

    token_response = hackatime.exchange_oauth_code(
        HACKATIME_CLIENT_ID, HACKATIME_CLIENT_SECRET, code, HACKATIME_REDIRECT_URI
    )
    access_token = token_response.get("access_token")
    if not access_token:
        logger.warning("Hackatime OAuth token exchange failed: %s", token_response)
        return redirect(url_for("homepage", error="Hackatime verification failed. Try again."))

    profile = hackatime.get_oauth_profile(access_token)
    if not profile:
        return redirect(url_for("homepage", error="Could not fetch your Hackatime profile. Try again."))

    if profile.get("slack_id") != slack_user_id:
        return redirect(url_for(
            "homepage",
            error="That Hackatime account isn't linked to this Slack account. "
                  "Log into the right one on hackatime.hackclub.com and try again.",
        ))

    hackatime_id = str(profile["id"])
    result = hackatime.get_streak_by_id(hackatime_id)
    if not result["ok"]:
        return redirect(url_for(
            "homepage",
            error="Verified your Hackatime account, but couldn't fetch stats with it automatically "
                  "-- enter your Hackatime username below instead.",
        ))

    db.link_user(slack_user_id, session.get("team_id", ""), hackatime_id, verified=True)
    return redirect(url_for("homepage", message="Verified and linked your Hackatime account."))


# ---------------------------------------------------------------------------
# Slack OAuth ("Add to Slack")
# ---------------------------------------------------------------------------

@app.route("/slack/install")
def slack_install():
    state = secrets.token_urlsafe(16)
    session["slack_oauth_state"] = state
    authorize_url = (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={SLACK_CLIENT_ID}"
        f"&scope={SLACK_BOT_SCOPES}"
        f"&redirect_uri={SLACK_REDIRECT_URI}"
        f"&state={state}"
    )
    return redirect(authorize_url)


@app.route("/slack/oauth/callback")
def slack_oauth_callback():
    if request.args.get("state") != session.pop("slack_oauth_state", None):
        return redirect(url_for("homepage", error="Slack login failed (state mismatch). Try again."))

    code = request.args.get("code")
    if not code:
        return redirect(url_for("homepage", error="Slack login was cancelled or failed."))

    response = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": SLACK_CLIENT_ID,
            "client_secret": SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": SLACK_REDIRECT_URI,
        },
        timeout=10,
    )
    data = response.json()
    if not data.get("ok"):
        logger.warning("Slack OAuth exchange failed: %s", data.get("error"))
        return redirect(url_for("homepage", error="Slack login failed. Try again."))

    team_id = data["team"]["id"]
    slack_user_id = data["authed_user"]["id"]
    # TODO: this stores the *installer's* bot token for completeness /
    # possible future multi-workspace support, but the bot and scheduler
    # processes currently just use the single SLACK_BOT_TOKEN env var
    # (this project only targets one Hack Club Slack -- see CLAUDE.md's
    # "Out of scope" section).
    db.save_installation(slack_user_id, team_id, data.get("access_token"))

    session["slack_user_id"] = slack_user_id
    session["team_id"] = team_id
    return redirect(url_for("homepage", message="Added to Slack! Now link your Hackatime username below."))


# ---------------------------------------------------------------------------
# Admin panel, gated by Hack Club Auth + an allowlist
# ---------------------------------------------------------------------------

def _is_admin():
    return session.get("is_admin", False)


@app.route("/admin")
def admin_dashboard():
    if not _is_admin():
        return redirect(url_for("admin_login"))
    return render_template(
        "admin_dashboard.html",
        users=db.list_linked_users(),
        job_runs=db.list_job_runs(),
        message=request.args.get("message"),
    )


@app.route("/admin/login")
def admin_login():
    redirect_uri = os.getenv("AUTH_REDIRECT_URI")
    return oauth.hackclub_auth.authorize_redirect(redirect_uri)


@app.route("/admin/callback")
def admin_callback():
    token = oauth.hackclub_auth.authorize_access_token()
    userinfo = token.get("userinfo") or oauth.hackclub_auth.userinfo(token=token)

    email = userinfo.get("email")
    slack_id = userinfo.get("slack_id")

    # Hack Club Auth proves *who this is*, not that they're allowed to
    # administer this bot -- that's the allowlist's job.
    if email not in ADMIN_ALLOWLIST and slack_id not in ADMIN_ALLOWLIST:
        return "Not authorized for the HackaStreak admin panel.", 403

    session["is_admin"] = True
    session["admin_email"] = email
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    session.pop("admin_email", None)
    return redirect(url_for("homepage"))


@app.route("/admin/run-job", methods=["POST"])
def admin_run_job():
    if not _is_admin():
        return redirect(url_for("admin_login"))
    result = run_daily_job()
    return redirect(
        url_for(
            "admin_dashboard",
            message=f"Job run complete: {result['users_checked']} checked, {result['users_skipped']} skipped.",
        )
    )


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if not _is_admin():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        db.set_setting("low_streak_threshold", request.form.get("low_streak_threshold", "1").strip())
        db.set_setting("milestones", request.form.get("milestones", "7,30,100,365").strip())
        return redirect(url_for("admin_settings", message="Settings saved."))

    return render_template(
        "admin_settings.html",
        low_streak_threshold=db.get_low_streak_threshold(),
        milestones=",".join(str(m) for m in db.get_milestones()),
        message=request.args.get("message"),
    )


@app.route("/admin/unlink/<slack_user_id>", methods=["POST"])
def admin_unlink(slack_user_id):
    if not _is_admin():
        return redirect(url_for("admin_login"))
    db.unlink_user(slack_user_id)
    return redirect(url_for("admin_dashboard", message=f"Unlinked {slack_user_id}."))


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
