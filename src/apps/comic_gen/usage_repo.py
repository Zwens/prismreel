import time
import uuid
from dataclasses import dataclass
from typing import Optional

from .auth_db import get_connection


LLM_USD_PER_10M_TOKENS = 64.0

# USD per 1,000,000 tokens, (price_without_video_input, price_with_video_input).
# "Time limited" discounted rows use the discounted price directly — this is
# a live rate table, not a historical record; update it when BytePlus's
# published pricing changes. See docs/plans/2026-09-11-usage-tracking-design.md
# for the source and date this was captured (2026-09-11).
SEEDANCE_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "dreamina-seedance-2-5-260628": {
        "480p": (10.70, 6.40),
        "720p": (10.70, 6.40),
        "1080p": (11.7, 7.0),
    },
    "dreamina-seedance-2-0-260128": {
        "480p": (7.0, 4.3),
        "720p": (7.0, 4.3),
        "1080p": (7.7, 4.7),
        "4k": (4.0, 2.4),
    },
    "dreamina-seedance-2-0-fast-260128": {
        "480p": (5.6, 3.3),
        "720p": (5.6, 3.3),
    },
    "dreamina-seedance-2-0-mini-260615": {
        "480p": (3.5, 2.1),
        "720p": (3.5, 2.1),
    },
}


def _llm_cost_usd(total_tokens: Optional[int]) -> Optional[float]:
    if total_tokens is None:
        return None
    return total_tokens / 10_000_000 * LLM_USD_PER_10M_TOKENS


def _seedance_cost_usd(
    model: str,
    resolution: Optional[str],
    input_has_video: Optional[bool],
    total_tokens: Optional[int],
) -> Optional[float]:
    if total_tokens is None or resolution is None:
        return None
    model_prices = SEEDANCE_PRICING.get(model)
    if not model_prices:
        return None
    price_pair = model_prices.get(resolution.lower())
    if not price_pair:
        return None
    price_per_million = price_pair[1] if input_has_video else price_pair[0]
    return total_tokens / 1_000_000 * price_per_million


@dataclass
class UsageEvent:
    id: str
    user_id: str
    kind: str
    provider: str
    model: Optional[str]
    resolution: Optional[str]
    input_has_video: Optional[bool]
    duration: Optional[int]
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
    duration: Optional[int] = None,
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
                (id, user_id, kind, provider, model, resolution, input_has_video, duration,
                 tokens_prompt, tokens_completion, total_tokens, cost_usd, count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                str(uuid.uuid4()), user_id, kind, provider, model, resolution,
                None if input_has_video is None else int(input_has_video),
                duration,
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
        total_tokens=total_tokens, cost_usd=_llm_cost_usd(total_tokens),
    )


def record_generation_usage(
    user_id: str,
    kind: str,
    provider: str,
    model: str,
    resolution: Optional[str] = None,
    input_has_video: Optional[bool] = None,
    duration: Optional[int] = None,
    total_tokens: Optional[int] = None,
) -> None:
    cost_usd = None
    if provider == "byteplus":
        cost_usd = _seedance_cost_usd(model, resolution, input_has_video, total_tokens)
    _insert(
        user_id=user_id, kind=kind, provider=provider, model=model,
        resolution=resolution, input_has_video=input_has_video, duration=duration,
        total_tokens=total_tokens, cost_usd=cost_usd,
    )


def _rows_to_summary(rows) -> dict:
    summary: dict = {}
    for row in rows:
        kind = row["kind"]
        provider = row["provider"]
        model = row["model"] or "unknown"
        # Video rows are split further by spec (resolution/input mode/duration)
        # since cost and duration vary per spec even for the same model.
        if kind == "video":
            spec_bits = [
                row["resolution"] or "unknown",
                "r2v" if row["input_has_video"] else "i2v",
                f"{row['duration']}s" if row["duration"] else "unknown",
            ]
            model_key = f"{model}__{'|'.join(spec_bits)}"
        else:
            model_key = model
        bucket = summary.setdefault(kind, {}).setdefault(provider, {}).setdefault(
            model_key,
            {
                "model": model,
                "resolution": row["resolution"] if kind == "video" else None,
                "input_has_video": bool(row["input_has_video"]) if kind == "video" else None,
                "duration": row["duration"] if kind == "video" else None,
                "count": 0,
                "total_tokens": None,
                "cost_usd": None,
            },
        )
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
