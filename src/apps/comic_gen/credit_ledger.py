import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from .auth_db import _DB_PATH, get_connection

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


def _get_locking_connection() -> sqlite3.Connection:
    """A connection with isolation_level=None (autocommit) so that we can
    issue our own explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK boundaries
    instead of relying on sqlite3's implicit transaction handling."""
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    return conn


def try_reserve_points(
    points: int, now_ts: Optional[float] = None, duration: int = 0
) -> Optional[str]:
    """Atomically check remaining quota and reserve ``points`` if enough is
    left, in a single SQLite transaction (BEGIN IMMEDIATE) to close the
    check-then-act race window between concurrent callers.

    Returns the reservation's ledger row id on success, or None if the
    current period does not have enough remaining points (in which case
    nothing is written).
    """
    now_ts = time.time() if now_ts is None else now_ts
    start, end = current_period(now_ts)

    conn = _get_locking_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS total FROM credit_ledger "
            "WHERE provider = 'deevid' AND created_at >= ? AND created_at <= ?",
            (start, end),
        ).fetchone()
        used = row["total"] or 0
        remaining = max(0, TOTAL_POINTS_PER_PERIOD - used)

        if points > remaining:
            conn.execute("ROLLBACK")
            return None

        reservation_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO credit_ledger (id, provider, points, duration, task_id, created_at) "
            "VALUES (?, 'deevid', ?, ?, NULL, ?)",
            (reservation_id, points, duration, now_ts),
        )
        conn.execute("COMMIT")
        return reservation_id
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def release_reservation(reservation_id: str) -> None:
    """Delete a previously reserved (but not consumed) ledger row, used when
    the downstream API call that the reservation was guarding fails.

    Uses the same 30s-timeout locking connection as try_reserve_points
    instead of get_connection()'s 5s sqlite3 default: under concurrent load
    a writer holding the lock for longer than 5s would otherwise make this
    raise sqlite3.OperationalError('database is locked'), masking the real
    generation failure and leaking the reservation forever."""
    conn = _get_locking_connection()
    try:
        conn.execute("DELETE FROM credit_ledger WHERE id = ?", (reservation_id,))
    finally:
        conn.close()


def record_manual_adjustment(points: int, note: str, now_ts: Optional[float] = None) -> str:
    """Record a manual correction for quota consumed outside this system
    (e.g. a generation run directly through DeeVid's own dashboard, which
    this system has no way to observe automatically since DeeVid's API
    exposes no balance-query endpoint).

    Unlike try_reserve_points, this always writes the full requested
    ``points`` even if it would push the period's usage past the 600-point
    cap -- the number represents what DeeVid's own dashboard says was
    really spent, not an estimate this system is choosing to reserve, so it
    must be recorded as-is. get_remaining_points()'s existing clamp-to-zero
    logic keeps the displayed remaining value from going negative.

    Returns the new ledger row's id. Raises ValueError for a non-positive
    points value (a manual correction should never *increase* the period's
    usage total by exactly a granting a negative charge; use a different
    mechanism if crediting a refund is ever needed)."""
    if points <= 0:
        raise ValueError("points must be positive")

    now_ts = time.time() if now_ts is None else now_ts
    adjustment_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO credit_ledger (id, provider, points, duration, task_id, created_at) "
            "VALUES (?, 'deevid', ?, 0, ?, ?)",
            (adjustment_id, points, f"manual-adjustment: {note}", now_ts),
        )
        conn.commit()
    finally:
        conn.close()
    return adjustment_id


def finalize_reservation(reservation_id: str, task_id: Optional[str]) -> None:
    """Attach the real provider task_id to a reservation once the API call
    that consumed it has succeeded. Does not change the reserved points.

    Uses the same 30s-timeout locking connection as try_reserve_points (see
    release_reservation for why the 5s get_connection() default is unsafe
    here)."""
    conn = _get_locking_connection()
    try:
        conn.execute(
            "UPDATE credit_ledger SET task_id = ? WHERE id = ?",
            (task_id, reservation_id),
        )
    finally:
        conn.close()
