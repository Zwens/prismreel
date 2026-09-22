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


def test_manual_adjustment_requires_login():
    client = _client()
    resp = client.post("/usage/deevid-credits/adjust", json={"points": 10, "note": "test"})
    assert resp.status_code == 401


def test_manual_adjustment_requires_admin_not_just_login():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("member@example.com", "pw123456", role="member")
    client = _client()
    client.post("/auth/login", json={"email": "member@example.com", "password": "pw123456"})

    resp = client.post("/usage/deevid-credits/adjust", json={"points": 10, "note": "test"})
    assert resp.status_code == 403


def test_manual_adjustment_by_admin_reduces_remaining():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("admin@example.com", "pw123456", role="admin")
    client = _client()
    client.post("/auth/login", json={"email": "admin@example.com", "password": "pw123456"})

    resp = client.post(
        "/usage/deevid-credits/adjust",
        json={"points": 10, "note": "DeeVid官網直接消耗"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["remaining"] == 590
    assert body["used"] == 10
    assert body["total"] == 600


def test_manual_adjustment_rejects_non_positive_points():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("admin2@example.com", "pw123456", role="admin")
    client = _client()
    client.post("/auth/login", json={"email": "admin2@example.com", "password": "pw123456"})

    resp = client.post(
        "/usage/deevid-credits/adjust",
        json={"points": 0, "note": "test"},
    )
    assert resp.status_code == 422

    resp2 = client.post(
        "/usage/deevid-credits/adjust",
        json={"points": -5, "note": "test"},
    )
    assert resp2.status_code == 422


def test_manual_adjustment_reflects_in_deevid_credits_endpoint():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("admin3@example.com", "pw123456", role="admin")
    client = _client()
    client.post("/auth/login", json={"email": "admin3@example.com", "password": "pw123456"})

    client.post("/usage/deevid-credits/adjust", json={"points": 10, "note": "x"})

    resp = client.get("/usage/deevid-credits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["used"] == 10
    assert body["remaining"] == 590
