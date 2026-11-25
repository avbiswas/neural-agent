import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "harness.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    source     TEXT NOT NULL,                 -- who woke the agent: 'cli', later 'telegram', 'timer'
    text       TEXT NOT NULL,
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
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    db.executescript(SCHEMA)
    return db
