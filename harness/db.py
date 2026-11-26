import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from croniter import croniter

DB_PATH = Path(__file__).parents[1] / "data" / "harness.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    source     TEXT NOT NULL,                 -- who woke the agent: 'cli', later 'telegram', 'timer'
    text       TEXT NOT NULL,
    model      TEXT,                          -- set by a timer: 'sonnet' | 'opus' (chat: always sonnet)
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending -> processing -> done | failed
    reply      TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    key        TEXT PRIMARY KEY,              -- a conversation, e.g. 'chat'
    session_id TEXT NOT NULL,                 -- the engine's session id
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS outbox (
    id         INTEGER PRIMARY KEY,
    channel    TEXT NOT NULL,                 -- where it goes: 'cli', later 'telegram'
    text       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending -> sent
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS timers (
    id         INTEGER PRIMARY KEY,
    prompt     TEXT NOT NULL,                 -- what the agent should do when it fires
    due_at     TEXT NOT NULL,                 -- UTC, same format as CURRENT_TIMESTAMP
    cron       TEXT,                          -- set for a schedule: '0 8 * * *' (local time)
    model      TEXT NOT NULL DEFAULT 'sonnet',  -- which model runs it: 'sonnet' | 'opus'
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending -> fired | cancelled (a schedule stays pending)
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS approvals (
    id         INTEGER PRIMARY KEY,
    channel    TEXT NOT NULL,                 -- where to ask: 'cli' or 'telegram'
    request    TEXT NOT NULL,                 -- what the agent wants to do, as the person sees it
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending -> approved | denied | expired
    shown      INTEGER NOT NULL DEFAULT 0,    -- the channel has put it in front of the person
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
DB_TIME = "%Y-%m-%d %H:%M:%S"  # how SQLite's CURRENT_TIMESTAMP writes UTC


def next_run(cron):
    """The next time a cron expression matches, counted from now, as a UTC db time.
    From now, not from the last run: after a long sleep a schedule fires once."""
    local_now = datetime.now().astimezone()
    return croniter(cron, local_now).get_next(datetime).astimezone(timezone.utc).strftime(DB_TIME)


def last_channel(db):
    """Where the person last talked to us ('cli', 'telegram'): replies the
    agent starts itself (send_message, timers) go there."""
    row = db.execute("""SELECT source FROM events WHERE source IN ('cli', 'telegram')
                        ORDER BY id DESC LIMIT 1""").fetchone()
    return row["source"] if row else "cli"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    db.executescript(SCHEMA)
    # Columns added after the first release: add them to an older database.
    for table, column in [("events", "model TEXT"), ("timers", "model TEXT NOT NULL DEFAULT 'sonnet'")]:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass  # already there
    return db
