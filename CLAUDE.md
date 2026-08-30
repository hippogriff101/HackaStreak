# CLAUDE.md — HackaStreak Redesign

Guidance for Claude Code when working in this repo. Read this before making changes.

## What this project is

HackaStreak is a Slack bot that reports a user's Hackatime coding streak. Hackatime is
a Hack Club project that logs coding time; this bot surfaces that data inside Slack.

**Current state (pre-redesign):**
- Single file, `viber.py`, using `slack-bolt` in Socket Mode.
- One feature: `/hackastreak [hackatime username]` slash command → calls the
  Hackatime API → replies with that user's streak, or an error if the user doesn't
  exist / has private stats.
- No database. No web server. No stored mapping between Slack users and Hackatime
  usernames — the caller has to type the Hackatime username every time.
- Hosted on a Pi Zero 2 W. Config via `.env` (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`).
- Deps: `requests`, `slack-bolt`, `python-dotenv`.

**Target state (this redesign):** turn it from a one-shot lookup command into a
persistent, identity-aware bot with four new features (below). This is a real
architecture change, not a patch — it needs a database and a small web app in
addition to the existing Slack bot process.

## New features to build

### 1. `@hackastreak [username]` mentions, replied to in-thread
- Move from slash-command-only to also handling `app_mention` events.
- Bot must be invited to channels (or use `app_mentions:read` + `chat:write` scopes).
- Reply using `thread_ts` (fall back to `ts` if the mention itself isn't already in
  a thread) so the response threads under the mention rather than posting a new
  top-level message.
- Keep the slash command working too — don't remove it, mentions are additive.

### 2. OAuth "Add to Slack" + homepage account linking
- A small web app (Flask or FastAPI) is a new component alongside the bot process.
- Flow:
  1. User installs the Slack app via standard OAuth (`Add to Slack` button) →
     workspace/user grant → store `slack_user_id`, `team_id`, and bot/user tokens.
  2. Homepage lets the now-identified Slack user link their **Hackatime username**,
     preferably by proving ownership rather than just typing it: Hackatime has its
     own OAuth app system (register at hackatime.hackclub.com → My OAuth Apps;
     `GET /oauth/authorize` → `POST /oauth/token` → `GET /api/v1/authenticated/me`
     returns `id`, `slack_id`, `github_username`, `emails` under the default
     `profile` scope). Cross-check the `slack_id` it returns against the
     `slack_user_id` from step 1 — if they match, the visitor has proven they own
     that Hackatime account. Fall back to a manually-typed username (checked only
     for existing/non-private, not ownership) if Hackatime OAuth isn't configured
     or the user prefers not to use it.
  3. Store the mapping (`slack_user_id` ↔ `hackatime_username`, plus whether it was
     verified via Hackatime OAuth or just typed) — this is what unlocks reminders
     and milestones, since the bot needs to know who to DM/watch without them
     re-typing their username every time.
- Treat Slack OAuth and "linking a Hackatime username" as two distinct steps — the
  Slack OAuth grant does not by itself prove which Hackatime account is theirs;
  that's what the Hackatime OAuth cross-check (or, failing that, the manual
  fallback) is for.
- The stats endpoint (`GET /api/v1/users/{user}/stats`) has historically been
  queried by a chosen public username. Whether it also accepts the numeric `id`
  from Hackatime OAuth's `/authenticated/me` hasn't been confirmed against a live
  account — treat that as an assumption to verify early, not a given.

### 3. Daily low-streak reminder DMs
- A scheduled job (daily cron — `APScheduler` in-process, a system cron hitting an
  endpoint, or a hosted scheduler) that:
  1. Iterates linked users.
  2. Fetches each one's current Hackatime streak.
  3. If below a configurable threshold, DMs them a reminder via `chat.postMessage`
     to their user ID (opens/reuses a DM channel).
- Needs per-user state to avoid spamming: track `last_reminded_date` so a user isn't
  DMed more than once per day, and consider letting users opt out.

### 4. Milestone announcements in a Slack channel
- Same daily job (or a separate check) compares each user's streak against a set of
  milestones (e.g. 7, 30, 100, 365 days).
- When a user crosses a milestone for the first time, post a celebratory message to
  a configured channel (`chat.postMessage` with the channel ID).
- Needs per-user state to avoid re-announcing: track which milestones have already
  been posted for each user (e.g. `milestones_hit: [7, 30]`).

### 5. Admin panel on the Flask app, gated by Hack Club Auth
- A separate `/admin` area of the same Flask app, protected by login via
  **Hack Club Auth** (`auth.hackclub.com`) rather than a bot-managed password.
- Register an OAuth/OIDC app at `https://auth.hackclub.com/developer/apps`. It's a
  standard OIDC provider — use its discovery document
  (`https://auth.hackclub.com/.well-known/openid-configuration`) with a library like
  `authlib` rather than hand-rolling the OAuth flow. Request scope
  `openid profile email slack_id verification_status` — the `slack_id` claim is
  worth having since it can be cross-referenced against this app's own Slack↔Hackatime
  mapping without asking the admin to re-enter anything.
- **Important distinction:** Hack Club Auth proves *who someone is* (a verified Hack
  Clubber), not that they're allowed to administer this specific bot. Gate `/admin`
  behind login **and** an allowlist check (e.g. `ADMIN_ALLOWLIST` env var of
  emails or `slack_id`s) — don't treat "logged in via Hack Club Auth" alone as
  authorization.
- Suggested admin capabilities, roughly in order of usefulness to build first:
  - View all linked users, their current streak, last-checked time, and reminder
    opt-in status.
  - Manually trigger the daily reminder/milestone job on demand (useful for testing
    and for recovering from a missed run).
  - Edit milestone thresholds and the low-streak reminder threshold without
    redeploying (pairs with the "admin-configurable milestones" idea from the
    suggestions section).
  - View recent job run history / errors (last run time, users skipped due to API
    errors, etc.) — this is the natural home for the `logging` output mentioned
    under Architecture notes, rather than only living in server logs.
  - Manually unlink a user (support request handling, without needing DB access).

## Data model (new)

A persistent store is required now — the old version was stateless. SQLite is fine
to start (matches the low-resource Pi hosting); structure it so it could move to
Postgres later without a rewrite.

Minimum fields per linked user:
- `slack_user_id`, `team_id`
- `hackatime_username`
- `hackatime_verified` (true if linked via Hackatime OAuth's slack_id cross-check,
  false if just typed in manually)
- `last_known_streak`, `last_checked_at`
- `last_reminded_date` (dedupe daily reminder DMs)
- `milestones_hit` (dedupe channel announcements)
- `reminder_opt_in` (bool, default true)

## Architecture notes

- This becomes at least two long-running things: the Slack bot process (events +
  slash command) and the small web app (OAuth callback + homepage + linking form).
  They share the same database.
- The daily job can live in either process — pick whichever is simpler to deploy
  given the Pi hosting, and say so in a comment where it's scheduled.
- Keep Hackatime API calls in one module — there's already error handling for
  nonexistent users / private stats / API errors in `viber.py`; reuse that logic
  rather than duplicating it across the mention handler, reminder job, and
  milestone job.
- Replace ad-hoc `print()` terminal output with `logging`, since the README already
  flags this as a known improvement to make.

## Conventions

- Python, `slack-bolt`, `.env` for secrets — keep consistent with the existing
  project rather than introducing a second framework.
- New env vars as this grows: `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`,
  `SLACK_SIGNING_SECRET`, `DATABASE_URL` (or SQLite path), `MILESTONE_CHANNEL_ID`,
  `LOW_STREAK_THRESHOLD`, plus `HACKATIME_CLIENT_ID`, `HACKATIME_CLIENT_SECRET`,
  `HACKATIME_REDIRECT_URI` (Hackatime OAuth, for the ownership-verified linking
  path), and for the admin panel: `AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET`,
  `AUTH_REDIRECT_URI`, `SESSION_SECRET` (Hack Club Auth + session signing), and
  `ADMIN_ALLOWLIST` (comma-separated emails or Slack user IDs permitted to reach
  `/admin` after logging in).
- Always refer to **Hack Club** in docs, comments, and UI copy — not "Hackclub",
  "hack club", or "HackClub".
- This project is openly described as partly vibe-coded and maintained by a
  student — prefer straightforward, well-commented code over clever abstractions,
  and leave TODOs where you make a judgment call instead of silently deciding.

## Suggested additions (not yet committed — flag for confirmation before building)

These extend the four core features above. None are required, but each solves a
gap the core features leave open once there are real linked users.

- **Timezone-aware scheduling.** The daily reminder/milestone job as described runs
  once at a fixed time for everyone, which means it lands at 3am for some users.
  Store a `timezone` (or just UTC offset) per linked user, captured on the homepage
  during linking, and schedule reminders relative to it rather than a single global
  cron time.
- **Leaderboard command / channel digest.** `/hackastreak leaderboard` (or a weekly
  auto-posted message) showing top current streaks in a channel. Cheap to build on
  top of data already being collected for milestones, and gives the bot a reason to
  be useful beyond individual lookups — this is the kind of social/competitive hook
  that tends to actually sustain daily coding habits in a Hack Club-style community.
- **Streak-reset / "comeback" message.** When a user's streak drops back to 0 after
  being nonzero, send one encouraging nudge rather than just silence. Keep this
  low-key and non-repetitive (once per reset, not once per day at 0) — the goal is
  encouragement, not guilt.
- **Privacy controls on the homepage.** Since the homepage now stores a Slack↔Hackatime
  mapping, give users a way to see what's stored and unlink/delete it themselves,
  not just an opt-in checkbox. Worth doing early since it's much easier to build
  alongside the initial linking flow than to retrofit later.
- **Hackatime API caching / rate-limit handling.** Once reminders and milestones run
  daily across every linked user, this is a lot more API traffic than the old
  one-shot slash command. Cache each user's last-fetched streak with a short TTL and
  handle 429s/backoff explicitly so one slow API day doesn't cascade into failed
  reminders for everyone.
- **`/hackastreak help` / self-serve onboarding.** A command that explains the
  `@mention` vs slash command vs homepage-linking flow. Once there are three ways to
  interact with the bot, users will need a quick way to find out what's available.
- **Admin-configurable milestones per workspace.** Rather than hardcoding
  7/30/100/365 globally, let a workspace admin set thresholds via the homepage.
  Only worth doing if this bot is expected to run in more than one Hack Club Slack —
  otherwise the env var approach from the core spec is enough.

## Hosting the finished version

Target: [Hack Club Nest](https://nest.hackclub.app), deployed as a `docker-compose.yml`
stack. Nest runs a Caddy reverse proxy on the host that maps a subdomain it assigns you
to a port on your instance, so there's no port-forwarding or tunnel container to manage
— `web` just needs to publish that port.

- **Three containers, one compose file:**
  - `bot` — Slack Bolt process (slash command + `app_mention` handling). Socket
    Mode means this container makes an outbound connection to Slack and needs no
    inbound port at all — no networking change needed for this one.
  - `web` — Flask app (Slack OAuth callback, homepage linking, admin panel). This
    is the one that needs a public HTTPS URL, since both Slack's OAuth redirect and
    Hack Club Auth's OAuth redirect call back to it from the outside. Publishes its
    port (`ports: ["${PORT}:${PORT}"]`) so Nest's host-level Caddy can reach it —
    the port must match whatever Nest assigned this subdomain to.
  - `scheduler` — small container running the daily reminder/milestone job (cron or
    a lightweight `APScheduler` loop), kept separate so a stuck job doesn't take
    down the bot or web app.
  - All three share one SQLite file via a named Docker volume (or a shared
    `DATABASE_URL` if this moves to Postgres later).

- **Callback URLs:** the callback URLs registered with Slack (`SLACK_REDIRECT_URI`)
  and Hack Club Auth (`AUTH_REDIRECT_URI`) must be `https://<your-nest-subdomain>/...`
  — Nest's Caddy is what terminates HTTPS, so these should never be an internal/LAN
  address or a raw `http://` port.

- **Dockerfile (per Python service — `bot`, `web`, `scheduler` can share this):**
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["python", "bot.py"]   # override per-service in compose (bot/web/scheduler)
  ```
  Standard x86_64 build here — no ARM/multi-arch concerns now that this isn't
  running on a Pi.

- **Persistence:** mount the SQLite file (or Postgres data dir) on a named volume
  so redeploying the stack doesn't wipe linked users and milestone history.
- **Config:** ship a `.env.example` listing every variable from the Conventions
  section above (including `AUTH_REDIRECT_URI` / `SLACK_REDIRECT_URI` set to the
  Nest subdomain's public URL, and `PORT` set to the port Nest assigned); load real
  secrets via a git-ignored `.env` referenced by `env_file:`.
- **Restart policy:** `restart: unless-stopped` on all services, so everything comes
  back up on its own after a host reboot.

## Out of scope for this redesign

- No mention of moving off Slack, changing the hosting setup, or supporting
  workspaces beyond a single Hack Club Slack unless explicitly asked.