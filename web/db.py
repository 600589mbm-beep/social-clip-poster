"""SQLite storage for channels, destination accounts, links, and post history."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT NOT NULL UNIQUE,
    platform     TEXT NOT NULL,              -- youtube | kick
    clip_seconds INTEGER NOT NULL DEFAULT 60,-- length of the auto-clip (from start)
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,               -- tiktok | instagram | facebook
    label       TEXT NOT NULL,               -- friendly name, e.g. "@mygamingclips"
    username    TEXT,                         -- IG username (if applicable)
    secret      TEXT,                         -- password/token entered directly (server-side, gitignored)
    secret_env  TEXT,                         -- OR name of env var holding password/token
    cookies_path TEXT,                        -- path to cookies file (TikTok) if applicable
    extra        TEXT,                        -- JSON for platform-specific fields (e.g. FB page_id)
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- which destination accounts a channel posts to
CREATE TABLE IF NOT EXISTS links (
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    PRIMARY KEY (channel_id, account_id)
);

-- every video id we've ever seen per channel (dedup so each posts once)
CREATE TABLE IF NOT EXISTS seen_videos (
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    video_id   TEXT NOT NULL,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (channel_id, video_id)
);

-- per-account post attempts/results
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    video_id   TEXT NOT NULL,
    video_url  TEXT,
    status     TEXT NOT NULL,                -- ok | error | skipped
    detail     TEXT,
    posted_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # migrate older DBs that predate the `secret` column
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        if "secret" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN secret TEXT")
    # keep the DB file private (it can hold credentials)
    try:
        DB_PATH.chmod(0o600)
    except OSError:
        pass


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB at {DB_PATH}")
