import time
import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, credit_ledger
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(credit_ledger)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _ts(year, month, day, hour=12):
    import datetime
    return datetime.datetime(year, month, day, hour, tzinfo=datetime.timezone.utc).timestamp()


def test_current_period_on_or_after_anchor_day():
    from src.apps.comic_gen import credit_ledger

    # 2026-09-25 落在 9/20 ~ 10/19 週期內
    start, end = credit_ledger.current_period(_ts(2026, 9, 25))
    assert start == _ts(2026, 9, 20, hour=0)
    expected_end = _ts(2026, 10, 20, hour=0) - 1
    assert abs(end - expected_end) < 2  # 允許次秒誤差


def test_current_period_before_anchor_day():
    from src.apps.comic_gen import credit_ledger

    # 2026-09-05 落在上月(8/20) ~ 本月(9/19) 週期內
    start, end = credit_ledger.current_period(_ts(2026, 9, 5))
    assert start == _ts(2026, 8, 20, hour=0)
    expected_end = _ts(2026, 9, 20, hour=0) - 1
    assert abs(end - expected_end) < 2


def test_current_period_crosses_year_boundary():
    from src.apps.comic_gen import credit_ledger

    # 2027-01-05 落在 2026-12-20 ~ 2027-01-19 週期內
    start, end = credit_ledger.current_period(_ts(2027, 1, 5))
    assert start == _ts(2026, 12, 20, hour=0)


def test_get_remaining_points_starts_full():
    from src.apps.comic_gen import credit_ledger

    assert credit_ledger.get_remaining_points(_ts(2026, 9, 25)) == 600


def test_record_usage_reduces_remaining():
    from src.apps.comic_gen import credit_ledger

    now = _ts(2026, 9, 25)
    credit_ledger.record_usage(points=20, duration=5, task_id="task-1")
    assert credit_ledger.get_remaining_points(now) == 580


def test_record_usage_outside_current_period_not_counted():
    from src.apps.comic_gen import credit_ledger, auth_db
    import uuid

    # 手动插入一笔属于「上一个周期」的记录（created_at 落在 8/25），
    # 確認 get_remaining_points 只加總「當前週期」範圍內的點數。
    conn = auth_db.get_connection()
    conn.execute(
        "INSERT INTO credit_ledger (id, provider, points, duration, task_id, created_at) "
        "VALUES (?, 'deevid', 100, 25, 'old-task', ?)",
        (str(uuid.uuid4()), _ts(2026, 8, 25)),
    )
    conn.commit()
    conn.close()

    assert credit_ledger.get_remaining_points(_ts(2026, 9, 25)) == 600


def test_get_remaining_points_never_negative():
    from src.apps.comic_gen import credit_ledger

    now = _ts(2026, 9, 25)
    for _ in range(31):
        credit_ledger.record_usage(points=20, duration=5, task_id=None)
    # 31 * 20 = 620 > 600，應 clamp 為 0 而非負數
    assert credit_ledger.get_remaining_points(now) == 0
