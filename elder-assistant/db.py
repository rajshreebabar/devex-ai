"""SQLite storage for contacts, reminders, appointments and notes."""
import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "assistant.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    relation TEXT DEFAULT '',
    phone TEXT NOT NULL,
    is_emergency INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    kind TEXT DEFAULT 'general',          -- medicine | appointment | call | general | alarm
    due_at TEXT NOT NULL,                 -- local time, 'YYYY-MM-DD HH:MM'
    repeat TEXT DEFAULT 'none',           -- none | daily
    done INTEGER DEFAULT 0,
    appt_id INTEGER
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor TEXT NOT NULL,
    date TEXT NOT NULL,                   -- 'YYYY-MM-DD'
    time TEXT NOT NULL,                   -- 'HH:MM'
    location TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def q(sql, args=()):
    """Run a SELECT and return a list of dicts."""
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def run(sql, args=()):
    """Run INSERT/UPDATE/DELETE. Returns (last_row_id, rows_changed)."""
    conn = _conn()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid, cur.rowcount
    finally:
        conn.close()
