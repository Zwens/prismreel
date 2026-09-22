import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo, user_repo, credit_ledger
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    importlib.reload(user_repo)
    importlib.reload(credit_ledger)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _client():
    from src.apps.comic_gen.api import app
    return TestClient(app)


def test_deevid_credits_requires_login():
    client = _client()
    resp = client.get("/usage/deevid-credits")
    assert resp.status_code == 401


def test_deevid_credits_returns_full_quota_when_unused():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("creditsuser@example.com", "pw123456")
    client = _client()
    client.post("/auth/login", json={"email": "creditsuser@example.com", "password": "pw123456"})

    resp = client.get("/usage/deevid-credits")

    assert resp.status_code == 200
    body = resp.json()
    assert body["used"] == 0
    assert body["remaining"] == 600
    assert body["total"] == 600
    assert "period_start" in body and "period_end" in body


def test_deevid_credits_reflects_recorded_usage():
    from src.apps.comic_gen import user_repo, credit_ledger

    user_repo.create_user("creditsuser2@example.com", "pw123456")
    credit_ledger.record_usage(points=20, duration=5, task_id="task-1")

    client = _client()
    client.post("/auth/login", json={"email": "creditsuser2@example.com", "password": "pw123456"})
    resp = client.get("/usage/deevid-credits")

    assert resp.status_code == 200
    body = resp.json()
    assert body["used"] == 20
    assert body["remaining"] == 580
