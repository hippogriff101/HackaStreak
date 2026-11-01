import sqlite3
import time
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    slack_id   TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

-- one row per interaction with the bot
-- kind: lookup | self | set | mention | pingword
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER NOT NULL,
    slack_id   TEXT NOT NULL,
    channel_id TEXT,
    kind       TEXT NOT NULL,
    detail     TEXT,
    outcome    TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


def set_username(slack_id, username):
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (slack_id, username, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(slack_id) DO UPDATE SET username = excluded.username, updated_at = excluded.updated_at",
            (slack_id, username, int(time.time())),
        )


def get_username(slack_id):
    with connect() as conn:
        row = conn.execute("SELECT username FROM users WHERE slack_id = ?", (slack_id,)).fetchone()
    return row["username"] if row else None


def log_event(slack_id, kind, channel_id=None, detail=None, outcome=None):
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (ts, slack_id, channel_id, kind, detail, outcome) VALUES (?, ?, ?, ?, ?, ?)",
            (int(time.time()), slack_id, channel_id, kind, detail, outcome),
        )


def stats():
    """Everything the admin home tab shows. Days are UTC."""
    now = int(time.time())
    today_start = now - now % 86400
    with connect() as conn:
        q = lambda sql, *args: conn.execute(sql, args).fetchall()
        one = lambda sql, *args: conn.execute(sql, args).fetchone()[0]
        return {
            "total": one("SELECT COUNT(*) FROM events"),
            "today": one("SELECT COUNT(*) FROM events WHERE ts >= ?", today_start),
            "week": one("SELECT COUNT(*) FROM events WHERE ts >= ?", today_start - 6 * 86400),
            "unique_users": one("SELECT COUNT(DISTINCT slack_id) FROM events"),
            "unique_today": one("SELECT COUNT(DISTINCT slack_id) FROM events WHERE ts >= ?", today_start),
            "linked_users": one("SELECT COUNT(*) FROM users"),
            "errors": one("SELECT COUNT(*) FROM events WHERE outcome = 'error'"),
            "by_kind": q("SELECT kind, COUNT(*) AS n FROM events GROUP BY kind ORDER BY n DESC"),
            "daily": q(
                "SELECT date(ts, 'unixepoch') AS day, COUNT(*) AS n, COUNT(DISTINCT slack_id) AS users "
                "FROM events WHERE ts >= ? GROUP BY day ORDER BY day",
                today_start - 6 * 86400,
            ),
            "top_users": q(
                "SELECT slack_id, COUNT(*) AS n, MAX(ts) AS last FROM events "
                "GROUP BY slack_id ORDER BY n DESC LIMIT 10"
            ),
            "top_lookups": q(
                "SELECT detail, COUNT(*) AS n FROM events WHERE kind IN ('lookup', 'self') AND detail IS NOT NULL "
                "GROUP BY lower(detail) ORDER BY n DESC LIMIT 10"
            ),
            "recent": q("SELECT * FROM events ORDER BY id DESC LIMIT 15"),
            "users": q("SELECT * FROM users ORDER BY updated_at DESC LIMIT 25"),
        }
