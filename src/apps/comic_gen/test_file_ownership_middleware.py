import pytest
from starlette.testclient import TestClient


def test_files_users_path_blocks_non_owner(monkeypatch):
    from src.apps.comic_gen import api

    class FakeUser:
        id = "user-2"
        role = "member"

    monkeypatch.setattr(api.auth, "get_current_user_from_cookie", lambda request: FakeUser())
    client = TestClient(api.app)
    resp = client.get("/files/users/user-1/some-project/frame.png")
    assert resp.status_code == 403


def test_files_users_path_allows_owner(monkeypatch, tmp_path):
    from src.apps.comic_gen import api
    import os

    os.makedirs("output/users/user-1/proj-x", exist_ok=True)
    with open("output/users/user-1/proj-x/test.txt", "w") as f:
        f.write("ok")

    class FakeUser:
        id = "user-1"
        role = "member"

    monkeypatch.setattr(api.auth, "get_current_user_from_cookie", lambda request: FakeUser())
    client = TestClient(api.app)
    resp = client.get("/files/users/user-1/proj-x/test.txt")
    assert resp.status_code == 200


def test_files_users_path_admin_bypasses(monkeypatch):
    from src.apps.comic_gen import api

    class AdminUser:
        id = "admin-id"
        role = "admin"

    monkeypatch.setattr(api.auth, "get_current_user_from_cookie", lambda request: AdminUser())
    client = TestClient(api.app)
    resp = client.get("/files/users/user-1/some-project/frame.png")
    assert resp.status_code != 403


def test_files_legacy_path_unaffected(monkeypatch):
    from src.apps.comic_gen import api
    client = TestClient(api.app)
    resp = client.get("/files/assets/does-not-exist.png")
    assert resp.status_code != 403
