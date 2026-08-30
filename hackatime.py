"""
Shared Hackatime API client.

Every process that needs a user's streak (the bot's slash command and
@mention handler, the daily reminder/milestone job, and the admin panel's
manual trigger) goes through get_streak() below, so the "user doesn't
exist" / "private stats" / "API is down" handling only lives in one place.
"""

import logging

import requests

logger = logging.getLogger(__name__)

HACKATIME_BASE_URL = "https://hackatime.hackclub.com/api/v1"


def _fetch_stats(identifier):
    """
    Shared implementation behind get_streak() and get_streak_by_id() -- the
    public stats endpoint takes the same {user} path slot either way, it's
    just a question of what the caller has on hand (a typed username, or a
    Hackatime OAuth user's numeric id).
    """
    try:
        response = requests.get(
            f"{HACKATIME_BASE_URL}/users/{identifier}/stats",
            headers={"accept": "application/json"},
            timeout=10,
        )
    except requests.exceptions.RequestException:
        logger.warning("Network error while contacting Hackatime for %s", identifier)
        return {
            "ok": False,
            "error": "network_error",
            "message": "Could not connect to Hackatime API.",
        }

    if response.status_code == 404:
        return {
            "ok": False,
            "error": "not_found",
            "message": f"User '{identifier}' does not exist.",
        }

    if response.status_code == 403:
        return {
            "ok": False,
            "error": "private",
            "message": f"User '{identifier}' has a private profile.",
        }

    if response.status_code != 200:
        logger.warning("Hackatime API returned %s for %s", response.status_code, identifier)
        return {
            "ok": False,
            "error": "api_error",
            "message": f"Hackatime API error ({response.status_code}). Try again later.",
        }

    try:
        data = response.json()
        streak = int(data["data"].get("streak", 0))
    except (ValueError, KeyError, TypeError):
        logger.warning("Unexpected Hackatime response shape for %s", identifier)
        return {
            "ok": False,
            "error": "api_error",
            "message": "Hackatime API returned an unexpected response. Try again later.",
        }

    return {"ok": True, "streak": streak}


def get_streak(hackatime_username):
    """
    Look up a Hackatime user's current streak by their public username.

    Returns a dict, always with an "ok" key:
      {"ok": True, "streak": 5}
      {"ok": False, "error": "not_found" | "private" | "api_error" | "network_error", "message": "..."}

    The "message" is a ready-to-send, human-readable string so callers
    (Slack replies, DMs) don't have to build their own copy per error type.
    """
    return _fetch_stats(hackatime_username)


def get_streak_by_id(hackatime_id):
    """
    Same as get_streak(), but for the numeric "id" a Hackatime OAuth token
    resolves to (see get_oauth_profile() below), for users who verified
    ownership instead of typing a username.

    ASSUMPTION, not confirmed against a live account: this treats the
    {user} path slot as accepting either a username or this numeric id, the
    same way many Wakatime-derived APIs do. If that turns out to be wrong,
    this will surface as a normal "not_found" error rather than crashing --
    worth an early real-world check once OAuth credentials exist.
    """
    return _fetch_stats(hackatime_id)


def exchange_oauth_code(client_id, client_secret, code, redirect_uri):
    """
    Exchange a Hackatime OAuth authorization code for an access token.
    POST https://hackatime.hackclub.com/oauth/token
    Returns the parsed JSON response (contains "access_token" on success).
    """
    response = requests.post(
        "https://hackatime.hackclub.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"accept": "application/json"},
        timeout=10,
    )
    return response.json()


def get_oauth_profile(access_token):
    """
    GET /api/v1/authenticated/me using a Hackatime OAuth access token.
    Returns a dict with "id", "slack_id", "github_username", "emails" on
    success, or None on failure. The "profile" scope (granted by default)
    is what unlocks this endpoint.
    """
    try:
        response = requests.get(
            f"{HACKATIME_BASE_URL}/authenticated/me",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=10,
        )
    except requests.exceptions.RequestException:
        logger.warning("Network error while fetching Hackatime OAuth profile")
        return None

    if response.status_code != 200:
        logger.warning("Hackatime OAuth profile lookup failed: %s", response.status_code)
        return None

    return response.json()
