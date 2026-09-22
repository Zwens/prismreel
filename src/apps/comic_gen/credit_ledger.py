import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from .auth_db import get_connection

PERIOD_ANCHOR_DAY = 20
TOTAL_POINTS_PER_PERIOD = 600


def current_period(now_ts: Optional[float] = None) -> Tuple[float, float]:
    """Return (period_start_ts, period_end_ts) anchored on the 20th of each month.

    If today's day-of-month >= PERIOD_ANCHOR_DAY, the period runs from this
    month's 20th through the day before next month's 20th. Otherwise it runs
    from last month's 20th through the day before this month's 20th.
    """
    now_ts = time.time() if now_ts is None else now_ts
    now = datetime.fromtimestamp(now_ts, tz=timezone.utc)

    if now.day >= PERIOD_ANCHOR_DAY:
        start_year, start_month = now.year, now.month
    else:
        start_month = now.month - 1
        start_year = now.year
        if start_month == 0:
            start_month = 12
            start_year -= 1

    period_start = datetime(start_year, start_month, PERIOD_ANCHOR_DAY, tzinfo=timezone.utc)

    end_month = start_month + 1
    end_year = start_year
    if end_month == 13:
        end_month = 1
        end_year += 1
    period_end_exclusive = datetime(end_year, end_month, PERIOD_ANCHOR_DAY, tzinfo=timezone.utc)

    return period_start.timestamp(), period_end_exclusive.timestamp() - 1


def get_remaining_points(now_ts: Optional[float] = None) -> int:
    """600 minus points already used in the current period, clamped to >= 0."""
    now_ts = time.time() if now_ts is None else now_ts
    start, end = current_period(now_ts)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS total FROM credit_ledger "
            "WHERE provider = 'deevid' AND created_at >= ? AND created_at <= ?",
            (start, end),
        ).fetchone()
        used = row["total"] or 0
    finally:
        conn.close()

    return max(0, TOTAL_POINTS_PER_PERIOD - used)


def record_usage(points: int, duration: int, task_id: Optional[str]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO credit_ledger (id, provider, points, duration, task_id, created_at) "
            "VALUES (?, 'deevid', ?, ?, ?, ?)",
            (str(uuid.uuid4()), points, duration, task_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
