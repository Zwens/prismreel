import time
import uuid
from dataclasses import dataclass
from typing import Optional

from .auth_db import get_connection


@dataclass
class UsageEvent:
    id: str
    user_id: str
    kind: str
    provider: str
    model: Optional[str]
    resolution: Optional[str]
    input_has_video: Optional[bool]
    tokens_prompt: Optional[int]
    tokens_completion: Optional[int]
    total_tokens: Optional[int]
    cost_usd: Optional[float]
    count: int
    created_at: float


def _insert(
    user_id: str,
    kind: str,
    provider: str,
    model: Optional[str],
    resolution: Optional[str] = None,
    input_has_video: Optional[bool] = None,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
    total_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO usage_events
                (id, user_id, kind, provider, model, resolution, input_has_video,
                 tokens_prompt, tokens_completion, total_tokens, cost_usd, count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                str(uuid.uuid4()), user_id, kind, provider, model, resolution,
                None if input_has_video is None else int(input_has_video),
                tokens_prompt, tokens_completion, total_tokens, cost_usd,
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_llm_usage(
    user_id: str,
    provider: str,
    model: str,
    tokens_prompt: Optional[int],
    tokens_completion: Optional[int],
    total_tokens: Optional[int],
) -> None:
    _insert(
        user_id=user_id, kind="llm", provider=provider, model=model,
        tokens_prompt=tokens_prompt, tokens_completion=tokens_completion,
        total_tokens=total_tokens,
    )


def record_generation_usage(
    user_id: str,
    kind: str,
    provider: str,
    model: str,
    resolution: Optional[str] = None,
    input_has_video: Optional[bool] = None,
    total_tokens: Optional[int] = None,
) -> None:
    _insert(
        user_id=user_id, kind=kind, provider=provider, model=model,
        resolution=resolution, input_has_video=input_has_video,
        total_tokens=total_tokens,
    )


def _rows_to_summary(rows) -> dict:
    summary: dict = {}
    for row in rows:
        kind = row["kind"]
        provider = row["provider"]
        model = row["model"] or "unknown"
        summary.setdefault(kind, {}).setdefault(provider, {}).setdefault(
            model, {"count": 0, "total_tokens": None, "cost_usd": None}
        )
        bucket = summary[kind][provider][model]
        bucket["count"] += row["count"]
        if row["total_tokens"] is not None:
            bucket["total_tokens"] = (bucket["total_tokens"] or 0) + row["total_tokens"]
        if row["cost_usd"] is not None:
            bucket["cost_usd"] = (bucket["cost_usd"] or 0.0) + row["cost_usd"]
    return summary


def get_user_usage_summary(user_id: str) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM usage_events WHERE user_id = ?", (user_id,)
        ).fetchall()
        return _rows_to_summary(rows)
    finally:
        conn.close()


def get_all_users_usage_summary() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM usage_events").fetchall()
        by_user: dict = {}
        for row in rows:
            uid = row["user_id"] or "unknown"
            by_user.setdefault(uid, []).append(row)
        return [
            {"user_id": uid, "summary": _rows_to_summary(rows)}
            for uid, rows in by_user.items()
        ]
    finally:
        conn.close()
