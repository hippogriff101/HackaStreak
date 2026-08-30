"""
SQLite data layer shared by the bot, web app, and scheduler processes.

Kept as plain sqlite3 + hand-written SQL rather than an ORM, in line with
this project staying simple. DATABASE_URL is just a filesystem path to the
SQLite file for now; if this ever moves to Postgres, only this module
should need to change.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "hackastreak.db")

DEFAULT_LOW_STREAK_THRESHOLD = int(os.getenv("LOW_STREAK_THRESHOLD", "1"))
DEFAULT_MILESTONES = os.getenv("MILESTONES", "7,30,100,365")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    db_dir = os.path.dirname(DATABASE_URL)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                slack_user_id TEXT PRIMARY KEY,
                team_id TEXT NOT NULL,
                hackatime_username TEXT NOT NULL,
                hackatime_verified INTEGER NOT NULL DEFAULT 0,
                last_known_streak INTEGER NOT NULL DEFAULT 0,
                last_checked_at TEXT,
                last_reminded_date TEXT,
                milestones_hit TEXT NOT NULL DEFAULT '',
                reminder_opt_in INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS slack_installations (
                slack_user_id TEXT PRIMARY KEY,
                team_id TEXT NOT NULL,
                access_token TEXT,
                installed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                users_checked INTEGER NOT NULL DEFAULT 0,
                users_skipped INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT
            );
            """
        )
        # Lightweight migration for DBs created before hackatime_verified existed.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "hackatime_verified" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN hackatime_verified INTEGER NOT NULL DEFAULT 0")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def today_iso():
    return date.today().isoformat()


# -- settings (admin-editable, fall back to env defaults on first run) ------

def get_setting(key, default):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_low_streak_threshold():
    return int(get_setting("low_streak_threshold", str(DEFAULT_LOW_STREAK_THRESHOLD)))


def get_milestones():
    raw = get_setting("milestones", DEFAULT_MILESTONES)
    return sorted(int(m) for m in raw.split(",") if m.strip())


# -- slack installations (from the "Add to Slack" OAuth grant) --------------

def save_installation(slack_user_id, team_id, access_token):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO slack_installations (slack_user_id, team_id, access_token, installed_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(slack_user_id) DO UPDATE SET "
            "team_id = excluded.team_id, access_token = excluded.access_token",
            (slack_user_id, team_id, access_token, _now_iso()),
        )


# -- linked users (slack_user_id <-> hackatime_username) --------------------

def link_user(slack_user_id, team_id, hackatime_username, verified=False):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (slack_user_id, team_id, hackatime_username, hackatime_verified)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(slack_user_id) DO UPDATE SET
                hackatime_username = excluded.hackatime_username,
                team_id = excluded.team_id,
                hackatime_verified = excluded.hackatime_verified
            """,
            (slack_user_id, team_id, hackatime_username, 1 if verified else 0),
        )


def unlink_user(slack_user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE slack_user_id = ?", (slack_user_id,))


def get_user(slack_user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE slack_user_id = ?", (slack_user_id,)
        ).fetchone()
        return dict(row) if row else None


def set_reminder_opt_in(slack_user_id, opt_in):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET reminder_opt_in = ? WHERE slack_user_id = ?",
            (1 if opt_in else 0, slack_user_id),
        )


def list_linked_users(opted_in_only=False):
    query = "SELECT * FROM users"
    if opted_in_only:
        query += " WHERE reminder_opt_in = 1"
    with get_conn() as conn:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]


def record_streak_check(slack_user_id, streak):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_known_streak = ?, last_checked_at = ? WHERE slack_user_id = ?",
            (streak, _now_iso(), slack_user_id),
        )


def mark_reminded_today(slack_user_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_reminded_date = ? WHERE slack_user_id = ?",
            (today_iso(), slack_user_id),
        )


def add_milestone_hit(slack_user_id, milestone, current_hits):
    hits = set(current_hits) | {milestone}
    serialized = ",".join(str(m) for m in sorted(hits))
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET milestones_hit = ? WHERE slack_user_id = ?",
            (serialized, slack_user_id),
        )


def parse_milestones_hit(raw):
    return {int(m) for m in raw.split(",") if m.strip()}


# -- job run history (for the admin panel) -----------------------------------

def start_job_run():
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO job_runs (started_at, status) VALUES (?, 'running')",
            (_now_iso(),),
        )
        return cursor.lastrowid


def finish_job_run(run_id, users_checked, users_skipped, error_summary=None):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE job_runs
            SET finished_at = ?, status = ?, users_checked = ?, users_skipped = ?, error_summary = ?
            WHERE id = ?
            """,
            (
                _now_iso(),
                "error" if error_summary else "ok",
                users_checked,
                users_skipped,
                error_summary,
                run_id,
            ),
        )


def list_job_runs(limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
