# HackaStreak

A Slack bot that tells you a user's current [Hackatime](https://hackatime.hackclub.com) streak, with
account linking, daily reminder DMs, and milestone shout-outs.

[Hackatime](https://hackatime.hackclub.com) is a Hack Club project that logs your coding time! As of
**now** I have [69 hours](https://hackatime.hackclub.com/freddie) coding on Hackatime.

This project is partly vibe-coded (new to `requests` and friends) but a fun one. Originally made with
GPT-5, GitHub Copilot and my fingers on a keyboard; the redesign below was built with Claude Code.

## How it works

Three long-running processes, one shared SQLite database:

- **`bot.py`** -- the Slack Bolt process (Socket Mode, no inbound port needed). Handles the
  `/hackastreak [hackatime username]` slash command and `@HackaStreak [username]` mentions
  (replied to in-thread). If you don't type a username and you've linked your account on the
  homepage, it'll use your linked username.
- **`webapp.py`** -- a small Flask app with three jobs:
  - "Add to Slack" OAuth, so the homepage knows which Slack user is filling out the linking form.
  - The homepage itself, where a linked Slack user either verifies ownership of a Hackatime account
    via Hackatime's own OAuth (matching its `slack_id` against the Slack account above) or falls back
    to typing/confirming a Hackatime username directly.
  - `/admin`, gated by [Hack Club Auth](https://auth.hackclub.com) + an email/Slack-ID allowlist,
    for viewing linked users, manually triggering the daily job, editing thresholds, and unlinking
    users.
- **`scheduler.py`** -- runs the daily job once a day (`DAILY_JOB_HOUR`, in UTC): checks every linked
  user's streak, DMs anyone below the low-streak threshold (once a day, opt-out available), and posts
  a milestone announcement the first time someone crosses 7/30/100/365 days (configurable in
  `/admin/settings`).

`hackatime.py`, `db.py`, and `jobs.py` are shared modules so the Hackatime API error handling and the
daily-job logic each live in exactly one place.

The original single-file version (`viber.py`, plus a couple of experiments) is preserved in
`older-stuff/` (gitignored) for reference.

## Running it locally

```
pip install -r requirements.txt
cp .env.example .env   # fill in real values, see below
python bot.py          # in one terminal
python webapp.py       # in another
python scheduler.py    # in a third, optional for local testing
```

### Setting up the pieces

1. **Slack app** ([api.slack.com/apps](https://api.slack.com/apps)): enable Socket Mode
   (`SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN`), add the `commands`, `app_mentions:read`, `chat:write`,
   and `im:write` bot scopes, subscribe to the `app_mention` event, and create the `/hackastreak`
   slash command. For the "Add to Slack" flow, also grab `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET` /
   `SLACK_SIGNING_SECRET` from the same app and set the OAuth redirect URL to your `SLACK_REDIRECT_URI`.
2. **Hackatime OAuth** (optional but recommended -- lets someone prove they own a Hackatime account
   instead of just typing a public username): register an app at
   [hackatime.hackclub.com](https://hackatime.hackclub.com) → My OAuth Apps, with redirect URI
   `https://<your-domain>/hackatime/oauth/callback` (`HACKATIME_REDIRECT_URI`), and set
   `HACKATIME_CLIENT_ID` / `HACKATIME_CLIENT_SECRET`. If left blank, the homepage's "Verify with
   Hackatime" button just won't work and everyone falls back to typing a username, same as before.
3. **Hack Club Auth** ([auth.hackclub.com/developer/apps](https://auth.hackclub.com/developer/apps)):
   register an app, request scope `openid profile email slack_id verification_status`, and set
   `AUTH_CLIENT_ID` / `AUTH_CLIENT_SECRET` / `AUTH_REDIRECT_URI` accordingly. Set `ADMIN_ALLOWLIST` to
   the emails or Slack user IDs allowed into `/admin` (Hack Club Auth proves who someone is, not that
   they're allowed to administer this bot -- the allowlist is what gates that).
4. **`SESSION_SECRET`**: any long random string, used to sign the Flask session cookie.

See `.env.example` for the full list of variables.

## Deploying

Hosted on [Hack Club Nest](https://nest.hackclub.app): three containers -- `bot`, `web`, `scheduler`
-- sharing one SQLite file over a named Docker volume, so redeploying doesn't wipe linked users or
milestone history. Nest's own Caddy reverse-proxies your assigned subdomain to a port on the host, so
`web` just needs that port published (`ports:` in `docker-compose.yml`, driven by the `PORT` env var)
-- no tunnel container needed. Point Slack's and Hack Club Auth's redirect URIs at
`https://<your-nest-subdomain>/...` (see the previous section).

```
docker compose up -d
```

(If deploying via Portainer instead of the CLI, paste `docker-compose.yml` into a new stack and load
`.env` as the stack's environment.)

## Not built yet (flagged, not decided against)

A few ideas from the design doc that extend this further but weren't part of this pass: per-user
timezone-aware scheduling (the daily job currently runs at one fixed UTC hour for everyone), a
leaderboard/digest command, a one-off "welcome back" message when a streak resets to 0, a fuller
privacy/data page on the homepage beyond the existing unlink button, Hackatime API response caching,
a `/hackastreak help` command, and per-workspace-configurable milestones (this only targets one Hack
Club Slack for now).
