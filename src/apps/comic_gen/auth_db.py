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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT,
                resolution TEXT,
                input_has_video INTEGER,
                duration INTEGER,
                tokens_prompt INTEGER,
                tokens_completion INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                count INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            )
            """
        )
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
        }
        if "duration" not in existing_columns:
            conn.execute("ALTER TABLE usage_events ADD COLUMN duration INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_ledger (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                points INTEGER NOT NULL,
                duration INTEGER NOT NULL,
                task_id TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        conn.commit()
