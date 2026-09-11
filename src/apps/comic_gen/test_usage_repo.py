import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def test_usage_events_table_exists():
    from src.apps.comic_gen import auth_db

    conn = auth_db.get_connection()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='usage_events'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_record_llm_usage_and_summary():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_llm_usage(
        user_id="u1", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=100, tokens_completion=50, total_tokens=150,
    )
    usage_repo.record_llm_usage(
        user_id="u1", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=200, tokens_completion=100, total_tokens=300,
    )
    summary = usage_repo.get_user_usage_summary("u1")
    assert summary["llm"]["dashscope"]["qwen3.7-plus"]["total_tokens"] == 450
    assert summary["llm"]["dashscope"]["qwen3.7-plus"]["count"] == 2


def test_record_generation_usage_count_only():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="kling", model="kling-v2",
    )
    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="kling", model="kling-v2",
    )
    summary = usage_repo.get_user_usage_summary("u1")
    assert summary["video"]["kling"]["kling-v2"]["count"] == 2
    assert summary["video"]["kling"]["kling-v2"]["total_tokens"] is None
    assert summary["video"]["kling"]["kling-v2"]["cost_usd"] is None


def test_empty_user_id_recorded_under_unknown_bucket():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_llm_usage(
        user_id="", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=10, tokens_completion=5, total_tokens=15,
    )
    all_summary = usage_repo.get_all_users_usage_summary()
    unknown_entry = next(u for u in all_summary if u["user_id"] in ("", "unknown"))
    assert unknown_entry["summary"]["llm"]["dashscope"]["qwen3.7-plus"]["count"] == 1


def test_get_all_users_usage_summary_groups_by_user():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_llm_usage(
        user_id="u1", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=10, tokens_completion=5, total_tokens=15,
    )
    usage_repo.record_llm_usage(
        user_id="u2", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=20, tokens_completion=10, total_tokens=30,
    )
    all_summary = usage_repo.get_all_users_usage_summary()
    ids = {u["user_id"] for u in all_summary}
    assert {"u1", "u2"}.issubset(ids)
