from unittest.mock import patch


def test_parse_novel_records_usage_when_user_id_given(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    from src.apps.comic_gen.llm import ScriptProcessor

    processor = ScriptProcessor()
    fake_json = '{"characters": [], "scenes": [], "props": []}'

    with patch.object(
        processor.llm, "chat_with_usage",
        return_value=(fake_json, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "qwen3.7-plus"),
    ):
        processor.parse_novel("Title", "Some novel text", user_id="user-123")

    summary = usage_repo.get_user_usage_summary("user-123")
    assert summary["llm"]["dashscope"]["qwen3.7-plus"]["total_tokens"] == 150


def test_parse_novel_no_user_id_records_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    from src.apps.comic_gen.llm import ScriptProcessor

    processor = ScriptProcessor()
    fake_json = '{"characters": [], "scenes": [], "props": []}'

    with patch.object(
        processor.llm, "chat_with_usage",
        return_value=(fake_json, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "qwen3.7-plus"),
    ):
        processor.parse_novel("Title", "Some novel text")  # no user_id — existing callers do this

    all_summary = usage_repo.get_all_users_usage_summary()
    assert all_summary == [] or all(u["user_id"] == "unknown" for u in all_summary)
