import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    importlib.reload(user_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _client():
    from src.apps.comic_gen.api import app
    return TestClient(app)


def test_polish_video_prompt_requires_login():
    client = _client()
    resp = client.post("/video/polish_prompt", json={"draft_prompt": "a cat walking"})
    assert resp.status_code == 401


def test_polish_video_prompt_works_when_logged_in(monkeypatch):
    from src.apps.comic_gen import user_repo
    from unittest.mock import patch

    user = user_repo.create_user("polish@example.com", "pw123456")
    client = _client()
    client.post("/auth/login", json={"email": "polish@example.com", "password": "pw123456"})

    with patch(
        "src.apps.comic_gen.llm.ScriptProcessor.polish_video_prompt",
        return_value={"prompt_cn": "一只猫在走路", "prompt_en": "a cat walking"},
    ) as mock_polish:
        resp = client.post("/video/polish_prompt", json={"draft_prompt": "a cat walking"})

    assert resp.status_code == 200
    assert resp.json()["prompt_en"] == "a cat walking"
    mock_polish.assert_called_once()
    assert mock_polish.call_args.kwargs["user_id"] == user.id


def test_polish_r2v_prompt_requires_login():
    client = _client()
    resp = client.post(
        "/video/polish_r2v_prompt",
        json={"draft_prompt": "a cat walking", "slots": [{"description": "雷震"}]},
    )
    assert resp.status_code == 401


def test_polish_r2v_prompt_works_when_logged_in(monkeypatch):
    from src.apps.comic_gen import user_repo
    from unittest.mock import patch

    user = user_repo.create_user("polishr2v@example.com", "pw123456")
    client = _client()
    client.post("/auth/login", json={"email": "polishr2v@example.com", "password": "pw123456"})

    with patch(
        "src.apps.comic_gen.llm.ScriptProcessor.polish_r2v_prompt",
        return_value={"prompt_cn": "一只猫在走路", "prompt_en": "a cat walking"},
    ) as mock_polish:
        resp = client.post(
            "/video/polish_r2v_prompt",
            json={"draft_prompt": "a cat walking", "slots": [{"description": "雷震"}]},
        )

    assert resp.status_code == 200
    assert resp.json()["prompt_en"] == "a cat walking"
    mock_polish.assert_called_once()
    assert mock_polish.call_args.kwargs["user_id"] == user.id
