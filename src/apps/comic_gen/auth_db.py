import os
import sqlite3
import threading

_DB_PATH = os.path.join("output", "auth.db")
_lock = threading.RLock()


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    with _lock:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                display_name TEXT,
                created_at REAL NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invites (
                code TEXT PRIMARY KEY,
                created_by TEXT NOT NULL REFERENCES users(id),
                email_hint TEXT,
                role TEXT NOT NULL DEFAULT 'member',
                created_at REAL NOT NULL,
                used_at REAL,
                used_by TEXT REFERENCES users(id)
            )
            """
        )
        conn.commit()
