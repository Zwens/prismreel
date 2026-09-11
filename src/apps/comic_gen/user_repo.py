import time
from dataclasses import dataclass
from typing import Optional

from .auth_db import get_connection
from .auth import hash_password, new_uuid


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    role: str
    display_name: Optional[str]
    created_at: float
    is_active: bool


def _row_to_user(row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=row["role"],
        display_name=row["display_name"],
        created_at=row["created_at"],
        is_active=bool(row["is_active"]),
    )


def create_user(email: str, password: str, role: str = "member", display_name: Optional[str] = None) -> User:
    conn = get_connection()
    try:
        user_id = new_uuid()
        created_at = time.time()
        password_hash = hash_password(password)
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, display_name, created_at, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, email, password_hash, role, display_name, created_at),
        )
        conn.commit()
        return User(user_id, email, password_hash, role, display_name, created_at, True)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def list_users() -> list[User]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        return [_row_to_user(r) for r in rows]
    finally:
        conn.close()


def set_password(user_id: str, new_password: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
        conn.commit()
    finally:
        conn.close()


def set_active(user_id: str, is_active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        conn.commit()
    finally:
        conn.close()


def create_invite(created_by: str, role: str = "member", email_hint: Optional[str] = None) -> str:
    conn = get_connection()
    try:
        code = new_uuid()
        conn.execute(
            "INSERT INTO invites (code, created_by, email_hint, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (code, created_by, email_hint, role, time.time()),
        )
        conn.commit()
        return code
    finally:
        conn.close()


def redeem_invite(code: str, email: str, password: str) -> User:
    conn = get_connection()
    try:
        invite = conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()
        if not invite:
            raise ValueError("Invalid invite code")
        if invite["used_at"] is not None:
            raise ValueError("Invite code already used")

        user_id = new_uuid()
        created_at = time.time()
        password_hash = hash_password(password)
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, display_name, created_at, is_active) VALUES (?, ?, ?, ?, NULL, ?, 1)",
            (user_id, email, password_hash, invite["role"], created_at),
        )
        conn.execute(
            "UPDATE invites SET used_at = ?, used_by = ? WHERE code = ?",
            (created_at, user_id, code),
        )
        conn.commit()
        return User(user_id, email, password_hash, invite["role"], None, created_at, True)
    finally:
        conn.close()
