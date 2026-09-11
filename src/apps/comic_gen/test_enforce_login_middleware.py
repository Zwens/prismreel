import pytest
from starlette.testclient import TestClient

_TEST_JWT_SECRET = "test-secret-at-least-32-characters-long"


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    from src.apps.comic_gen import auth_db
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def test_protected_endpoint_401_without_cookie(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", _TEST_JWT_SECRET)
    import importlib
    from src.apps.comic_gen import api
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.get("/projects/")
    assert resp.status_code == 401


def test_auth_login_endpoint_accessible_without_cookie(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", _TEST_JWT_SECRET)
    import importlib
    from src.apps.comic_gen import api
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
    assert resp.status_code != 401 or resp.json().get("detail") != "Not authenticated"


def test_health_endpoint_accessible_without_cookie(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", _TEST_JWT_SECRET)
    import importlib
    from src.apps.comic_gen import api
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code != 401


def test_login_gate_disabled_when_jwt_secret_unset(monkeypatch):
    monkeypatch.delenv("PRISMREEL_JWT_SECRET", raising=False)
    import importlib
    from src.apps.comic_gen import api, auth
    importlib.reload(auth)
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.get("/projects/")
    assert resp.status_code != 401
